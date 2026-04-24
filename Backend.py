from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Optional
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATABASE_URL = "sqlite:///./pet_pulse.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ─── DB MODELS ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String); email = Column(String, unique=True, index=True)
    password = Column(String); role = Column(String, default="pet_owner")

class Pet(Base):
    __tablename__ = "pets"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer); name = Column(String)
    type = Column(String); age = Column(String)

class MarketplaceItem(Base):
    __tablename__ = "marketplace"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String); breed = Column(String); price = Column(Integer)
    seller_id = Column(Integer); seller_name = Column(String)
    status = Column(String, default="available")

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    vet_id = Column(Integer); pet_id = Column(Integer)
    pet_name = Column(String); time = Column(String)
    status = Column(String, default="pending")

class ShelterAnimal(Base):
    __tablename__ = "shelter_animals"
    id = Column(Integer, primary_key=True, index=True)
    shelter_id = Column(Integer); name = Column(String); type = Column(String)
    status = Column(String, default="In Care"); intake_date = Column(String)

class AdoptionRequest(Base):
    __tablename__ = "adoption_requests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer); user_name = Column(String)
    pet_id = Column(Integer); pet_name = Column(String)
    shelter_id = Column(Integer); status = Column(String, default="pending")
    message = Column(String)

class MedicalRecord(Base):
    __tablename__ = "medical_records"
    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer); date = Column(String)
    diagnosis = Column(String); treatment = Column(String); vet_name = Column(String)

class DietLog(Base):
    __tablename__ = "diet_logs"
    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer); food_item = Column(String)
    amount = Column(String); timestamp = Column(String)

class PanicAlert(Base):
    __tablename__ = "panic_alerts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer); pet_name = Column(String)
    location = Column(String); description = Column(String)
    status = Column(String, default="active")

class ForumPost(Base):
    __tablename__ = "forum_posts"
    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String); content = Column(String); timestamp = Column(String)

Base.metadata.create_all(bind=engine)

# ─── APP SETUP ────────────────────────────────────────────────────────────────

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# ─── PYDANTIC SCHEMAS ─────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name: str; email: str; password: str; role: str = "pet_owner"

class LoginRequest(BaseModel):
    email: str; password: str

class PetCreate(BaseModel):
    owner_id: int; name: str; type: str; age: str

class PetUpdate(BaseModel):
    name: str; type: str; age: str

class MarketCreate(BaseModel):
    name: str; breed: str; price: int; seller_id: int; seller_name: str

class AppointmentCreate(BaseModel):
    vet_id: int; pet_id: int; pet_name: str; time: str

class AnimalCreate(BaseModel):
    shelter_id: int; name: str; type: str; intake_date: str

class AdoptionCreate(BaseModel):
    user_id: int; user_name: str; pet_id: int
    pet_name: str; shelter_id: int; message: str

class MedicalCreate(BaseModel):
    pet_id: int; date: str; diagnosis: str; treatment: str; vet_name: str

class DietCreate(BaseModel):
    pet_id: int; food_item: str; amount: str; timestamp: str

class PanicCreate(BaseModel):
    user_id: int; pet_name: str; location: str; description: str

class ForumCreate(BaseModel):
    user_name: str; content: str; timestamp: str

class ChatRequest(BaseModel):
    message: str
    pet_info: Optional[str] = None

# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.post("/signup")
def signup(user_data: SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(400, "Email already registered.")
    u = User(name=user_data.name, email=user_data.email, password=user_data.password, role=user_data.role)
    db.add(u); db.commit(); db.refresh(u)
    return {"message": "Account created!", "user": u.name, "role": u.role}

@app.post("/login")
def login(c: LoginRequest, db: Session = Depends(get_db)):
    if c.email == "Umar" and c.password == "123456":
        return {"message": "ok", "user": {"id": 9999, "name": "Umar (Admin)", "email": "admin@petpulse.com", "role": "admin"}}
    if c.email == "vet" and c.password == "123456":
        return {"message": "ok", "user": {"id": 9998, "name": "Dr. Smith", "email": "vet@petpulse.com", "role": "doctor"}}
    u = db.query(User).filter(User.email == c.email).first()
    if not u or u.password != c.password:
        raise HTTPException(401, "Invalid credentials")
    return {"message": "ok", "user": {"id": u.id, "name": u.name, "email": u.email, "role": u.role}}

# ─── PETS ─────────────────────────────────────────────────────────────────────

@app.get("/pets")
def get_pets(owner_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Pet)
    if owner_id is not None: q = q.filter(Pet.owner_id == owner_id)
    return q.all()

@app.post("/pets")
def add_pet(pet: PetCreate, db: Session = Depends(get_db)):
    p = Pet(**pet.dict()); db.add(p); db.commit(); db.refresh(p); return p

@app.put("/pets/{pet_id}")
def update_pet(pet_id: int, data: PetUpdate, db: Session = Depends(get_db)):
    p = db.query(Pet).filter(Pet.id == pet_id).first()
    if not p: raise HTTPException(404, "Pet not found")
    p.name = data.name; p.type = data.type; p.age = data.age
    db.commit(); return p

@app.delete("/pets/{pet_id}")
def delete_pet(pet_id: int, db: Session = Depends(get_db)):
    p = db.query(Pet).filter(Pet.id == pet_id).first()
    if p: db.delete(p); db.commit()
    return {"message": "Pet deleted"}

# ─── MARKETPLACE ──────────────────────────────────────────────────────────────

@app.get("/marketplace")
def get_marketplace(status: Optional[str] = None, seller_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(MarketplaceItem)
    if status: q = q.filter(MarketplaceItem.status == status)
    if seller_id is not None: q = q.filter(MarketplaceItem.seller_id == seller_id)
    return q.all()

@app.post("/marketplace")
def add_marketplace(item: MarketCreate, db: Session = Depends(get_db)):
    i = MarketplaceItem(**item.dict()); db.add(i); db.commit(); db.refresh(i); return i

@app.delete("/marketplace/{item_id}")
def delete_listing(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MarketplaceItem).filter(MarketplaceItem.id == item_id).first()
    if item: db.delete(item); db.commit()
    return {"message": "Listing removed"}

@app.put("/marketplace/{item_id}/buy")
def buy_item(item_id: int, buyer_id: int, db: Session = Depends(get_db)):
    item = db.query(MarketplaceItem).filter(MarketplaceItem.id == item_id).first()
    if not item: raise HTTPException(404, "Not found")
    if item.status != "available": raise HTTPException(400, "Already sold")
    item.status = "sold"
    new_pet = Pet(owner_id=buyer_id, name=item.name, type=item.breed, age="Unknown")
    db.add(new_pet); db.commit()
    return {"message": "Purchase successful"}

# ─── VET APPOINTMENTS ─────────────────────────────────────────────────────────

@app.get("/vet_appointments")
def get_appointments(vet_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Appointment)
    if vet_id is not None: q = q.filter(Appointment.vet_id == vet_id)
    return q.all()

@app.post("/vet_appointments")
def book_appointment(a: AppointmentCreate, db: Session = Depends(get_db)):
    appt = Appointment(**a.dict()); db.add(appt); db.commit(); db.refresh(appt); return appt

@app.delete("/vet_appointments/{appt_id}")
def cancel_appointment(appt_id: int, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if a: db.delete(a); db.commit()
    return {"message": "Appointment cancelled"}

@app.put("/vet_appointments/{appt_id}/complete")
def complete_appointment(appt_id: int, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not a: raise HTTPException(404, "Not found")
    a.status = "completed"; db.commit(); return a

# ─── SHELTER ANIMALS ──────────────────────────────────────────────────────────

@app.get("/shelter_animals")
def get_shelter_animals(shelter_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(ShelterAnimal)
    if shelter_id is not None: q = q.filter(ShelterAnimal.shelter_id == shelter_id)
    return q.all()

@app.post("/shelter_animals")
def add_shelter_animal(a: AnimalCreate, db: Session = Depends(get_db)):
    animal = ShelterAnimal(**a.dict()); db.add(animal); db.commit(); db.refresh(animal); return animal

@app.put("/shelter_animals/{animal_id}/status")
def update_animal_status(animal_id: int, status: str, db: Session = Depends(get_db)):
    a = db.query(ShelterAnimal).filter(ShelterAnimal.id == animal_id).first()
    if not a: raise HTTPException(404, "Not found")
    a.status = status; db.commit(); return a

@app.delete("/shelter_animals/{animal_id}")
def delete_shelter_animal(animal_id: int, db: Session = Depends(get_db)):
    a = db.query(ShelterAnimal).filter(ShelterAnimal.id == animal_id).first()
    if a: db.delete(a); db.commit()
    return {"message": "Deleted"}

# ─── ADOPTION REQUESTS ────────────────────────────────────────────────────────

@app.get("/adoption_requests")
def get_adoption_requests(shelter_id: Optional[int] = None, user_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(AdoptionRequest)
    if shelter_id is not None: q = q.filter(AdoptionRequest.shelter_id == shelter_id)
    if user_id is not None: q = q.filter(AdoptionRequest.user_id == user_id)
    return q.all()

@app.post("/adoption_requests")
def create_adoption_request(req: AdoptionCreate, db: Session = Depends(get_db)):
    r = AdoptionRequest(**req.dict()); db.add(r); db.commit(); db.refresh(r); return r

@app.put("/adoption_requests/{req_id}")
def update_adoption_status(req_id: int, status: str, db: Session = Depends(get_db)):
    r = db.query(AdoptionRequest).filter(AdoptionRequest.id == req_id).first()
    if not r: raise HTTPException(404, "Not found")
    r.status = status; db.commit(); return r

@app.delete("/adoption_requests/{req_id}")
def delete_adoption_request(req_id: int, db: Session = Depends(get_db)):
    r = db.query(AdoptionRequest).filter(AdoptionRequest.id == req_id).first()
    if r: db.delete(r); db.commit()
    return {"message": "Request withdrawn"}

# ─── MEDICAL RECORDS ──────────────────────────────────────────────────────────

@app.get("/medical_records/{pet_id}")
def get_medical_records(pet_id: int, db: Session = Depends(get_db)):
    return db.query(MedicalRecord).filter(MedicalRecord.pet_id == pet_id).all()

@app.post("/medical_records")
def add_medical_record(rec: MedicalCreate, db: Session = Depends(get_db)):
    r = MedicalRecord(**rec.dict()); db.add(r); db.commit(); db.refresh(r); return r

@app.delete("/medical_records/{rec_id}")
def delete_medical_record(rec_id: int, db: Session = Depends(get_db)):
    r = db.query(MedicalRecord).filter(MedicalRecord.id == rec_id).first()
    if r: db.delete(r); db.commit()
    return {"message": "Deleted"}

# ─── DIET LOGS ────────────────────────────────────────────────────────────────

@app.get("/diet_logs/{pet_id}")
def get_diet_logs(pet_id: int, db: Session = Depends(get_db)):
    return db.query(DietLog).filter(DietLog.pet_id == pet_id).all()

@app.post("/diet_logs")
def add_diet_log(log: DietCreate, db: Session = Depends(get_db)):
    l = DietLog(**log.dict()); db.add(l); db.commit(); db.refresh(l); return l

@app.delete("/diet_logs/{log_id}")
def delete_diet_log(log_id: int, db: Session = Depends(get_db)):
    l = db.query(DietLog).filter(DietLog.id == log_id).first()
    if l: db.delete(l); db.commit()
    return {"message": "Deleted"}

# ─── PANIC ALERTS ─────────────────────────────────────────────────────────────

@app.get("/panic_alerts")
def get_panic_alerts(db: Session = Depends(get_db)):
    return db.query(PanicAlert).filter(PanicAlert.status == "active").all()

@app.get("/panic_alerts/all")
def get_all_panic_alerts(db: Session = Depends(get_db)):
    return db.query(PanicAlert).order_by(PanicAlert.id.desc()).all()

@app.post("/panic_alerts")
def create_panic_alert(a: PanicCreate, db: Session = Depends(get_db)):
    alert = PanicAlert(**a.dict()); db.add(alert); db.commit(); db.refresh(alert); return alert

@app.put("/panic_alerts/{alert_id}/resolve")
def resolve_panic_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.query(PanicAlert).filter(PanicAlert.id == alert_id).first()
    if not a: raise HTTPException(404, "Not found")
    a.status = "resolved"; db.commit(); return a

@app.delete("/panic_alerts/{alert_id}")
def delete_panic_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.query(PanicAlert).filter(PanicAlert.id == alert_id).first()
    if a: db.delete(a); db.commit()
    return {"message": "Deleted"}

# ─── FORUM ────────────────────────────────────────────────────────────────────

@app.get("/forum_posts")
def get_forum_posts(db: Session = Depends(get_db)):
    return db.query(ForumPost).order_by(ForumPost.id.asc()).all()

@app.post("/forum_posts")
def add_forum_post(post: ForumCreate, db: Session = Depends(get_db)):
    p = ForumPost(**post.dict()); db.add(p); db.commit(); db.refresh(p); return p

@app.delete("/forum_posts/{post_id}")
def delete_forum_post(post_id: int, db: Session = Depends(get_db)):
    p = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if p: db.delete(p); db.commit()
    return {"message": "Deleted"}

# ─── AI CHATBOT ───────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat_with_ai(req: ChatRequest):
    if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your_openai_api_key_here":
        return {"reply": "AI Assistant is not configured. Please add your OpenAI API Key to the .env file."}
    
    try:
        system_prompt = (
            "You are a helpful pet nutrition expert assistant for the PetPulse platform. "
            "Your goal is to provide precise, short, and practical diet suggestions for pets. "
            "Keep your answers very small and to the point. If you don't know something, suggest seeing a vet."
        )
        
        user_message = req.message
        if req.pet_info:
            user_message = f"Pet Info: {req.pet_info}\n\nUser Question: {user_message}"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return {"reply": "Sorry, I'm having trouble connecting to my brain right now. Try again later!"}

# ─── ADMIN ────────────────────────────────────────────────────────────────────

@app.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if u: db.delete(u); db.commit()
    return {"message": "User removed"}

@app.get("/admin/stats")
def get_admin_stats(db: Session = Depends(get_db)):
    return {
        "users": db.query(User).count(),
        "vets": db.query(User).filter(User.role == "doctor").count(),
        "shelters": db.query(User).filter(User.role == "shelter").count(),
        "pets": db.query(Pet).count(),
        "marketplace": db.query(MarketplaceItem).count(),
        "appointments": db.query(Appointment).count(),
        "alerts": db.query(PanicAlert).filter(PanicAlert.status == "active").count(),
        "forum_posts": db.query(ForumPost).count(),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)