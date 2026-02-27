from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from pydantic import BaseModel
from typing import List, Optional
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

# --- CONFIGURAZIONE DATABASE ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./links_dashboard.db"
Base = declarative_base()

# classi SQLAlchemy per Tab, Category e Link con relazioni appropriate


class Tab(Base):
    __tablename__ = "tabs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    categories = relationship(
        "Category", back_populates="tab", cascade="all, delete")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    tab_id = Column(Integer, ForeignKey("tabs.id"))
    tab = relationship("Tab", back_populates="categories")
    links = relationship("Link", back_populates="category",
                         cascade="all, delete")


class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    url = Column(String)
    description = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    category = relationship("Category", back_populates="links")


engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={
                       "check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- LIFESPAN (Nuovo metodo al posto di on_event) ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Crea tabelle
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Controlliamo se la Tab "Work" esiste già per evitare duplicati
        if not db.query(Tab).filter(Tab.name == "Work").first():
            # 1. Creazione Tab
            work = Tab(name="Work")
            personal = Tab(name="Personal")
            db.add_all([work, personal])
            db.commit()
            db.refresh(work)
            db.refresh(personal)

            # 2. Creazione Categorie per Work
            dev_tools = Category(name="Dev Tools", tab_id=work.id)
            social_work = Category(name="Social", tab_id=work.id)
            db.add_all([dev_tools, social_work])
            db.commit()
            db.refresh(dev_tools)

            # 3. Creazione Categorie per Personal
            social_pers = Category(name="Social", tab_id=personal.id)
            web_tools = Category(name="Web Tools", tab_id=personal.id)
            db.add_all([social_pers, web_tools])
            db.commit()
            db.refresh(dev_tools)
            db.refresh(social_pers)

            # 4. Inserimento Link di esempio
            links = [
                # Link per Work -> Dev Tools
                Link(name="GitHub", url="https://github.com",
                     description="Code repositories", category_id=dev_tools.id),
                Link(name="Stack Overflow", url="https://stackoverflow.com",
                     description="Q&A for developers", category_id=dev_tools.id),

                # Link per Work -> Social
                Link(name="LinkedIn", url="https://linkedin.com",
                     description="Professional network", category_id=social_work.id),

                # Link per Personal -> Social
                Link(name="Facebook", url="https://facebook.com",
                     description="Il mio Facebook", category_id=social_pers.id),
                Link(name="Instagram", url="https://instagram.com",
                     description="Il mio Instagram", category_id=social_pers.id),
                Link(name="Sito Itis", url="https://www.itiscastelli.edu.it/",
                     description="Il sito dell'Itis Castelli", category_id=social_pers.id),

                # Link per Personal -> Web Tools
                Link(name="Personal Site", url="https://www.mauriziocozzetto.it",
                     description="Il mio sito", category_id=web_tools.id)
            ]
            db.add_all(links)
            db.commit()

    finally:
        db.close()

    yield

# --- SCHEMI PYDANTIC (Aggiornati a V2) ---


class LinkSchema(BaseModel):
    id: Optional[int] = None
    name: str
    url: str
    description: Optional[str] = None
    category_id: int

    class Config:
        from_attributes = True


class CategorySchema(BaseModel):
    id: Optional[int] = None
    name: str
    tab_id: int
    links: List[LinkSchema] = []

    class Config:
        from_attributes = True


class TabSchema(BaseModel):
    id: int
    name: str
    categories: List[CategorySchema] = []

    class Config:
        from_attributes = True


# --- API APP ---
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- ROTTE API ---


@app.get("/")
# devi usare ResponseFile per restituire un file statico
def read_root():
    return FileResponse("index.html")


@app.get("/api/tabs", response_model=List[TabSchema])
def get_all_data(db: Session = Depends(get_db)):
    return db.query(Tab).all()


@app.post("/api/categories")
def create_category(cat: CategorySchema, db: Session = Depends(get_db)):
    new_cat = Category(name=cat.name, tab_id=cat.tab_id)
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    return new_cat


@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(404)
    db.delete(cat)
    db.commit()
    return {"status": "deleted"}


@app.post("/api/links")
def add_link(link: LinkSchema, db: Session = Depends(get_db)):
    # .model_dump() è il nuovo .dict() in Pydantic V2
    new_link = Link(**link.model_dump(exclude={'id'}))
    db.add(new_link)
    db.commit()
    db.refresh(new_link)
    return new_link


@app.delete("/api/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(404)
    db.delete(link)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/search")
def search_links(q: str, db: Session = Depends(get_db)):
    return db.query(Link).filter(Link.name.ilike(f"%{q}%")).all()


@app.put("/api/links/{link_id}")
def update_link(link_id: int, updated_link: LinkSchema, db: Session = Depends(get_db)):
    db_link = db.query(Link).filter(Link.id == link_id).first()
    if not db_link:
        raise HTTPException(status_code=404, detail="Link not found")

    # Aggiorna i campi
    db_link.name = updated_link.name
    db_link.url = updated_link.url
    db_link.description = updated_link.description

    db.commit()
    db.refresh(db_link)
    return db_link


# ... (Mantieni i modelli e la configurazione DB precedente) ...

# --- NUOVE ROTTE TABS ---

@app.post("/api/tabs")
def create_tab(tab: TabSchema, db: Session = Depends(get_db)):
    new_tab = Tab(name=tab.name)
    db.add(new_tab)
    db.commit()
    db.refresh(new_tab)
    return new_tab


@app.put("/api/tabs/{tab_id}")
def update_tab(tab_id: int, updated_tab: TabSchema, db: Session = Depends(get_db)):
    db_tab = db.query(Tab).filter(Tab.id == tab_id).first()
    if not db_tab:
        raise HTTPException(404)
    db_tab.name = updated_tab.name
    db.commit()
    return db_tab


@app.delete("/api/tabs/{tab_id}")
def delete_tab(tab_id: int, db: Session = Depends(get_db)):
    db_tab = db.query(Tab).filter(Tab.id == tab_id).first()
    if not db_tab:
        raise HTTPException(404)
    db.delete(db_tab)
    db.commit()
    return {"status": "deleted"}

# --- AGGIORNAMENTO CATEGORIA ---


@app.put("/api/categories/{cat_id}")
def update_category(cat_id: int, updated_cat: CategorySchema, db: Session = Depends(get_db)):
    db_cat = db.query(Category).filter(Category.id == cat_id).first()
    if not db_cat:
        raise HTTPException(404)
    db_cat.name = updated_cat.name
    db.commit()
    return db_cat
