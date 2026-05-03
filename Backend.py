"""
PetPulse Backend - FastAPI Server
Handles Authentication, Pet Management, Marketplace, Medical Records, Vaccinations, and AI Chatbot.
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Optional
import os
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file (e.g. DATABASE_URL)
load_dotenv()

# ─── DATABASE CONFIGURATION ───────────────────────────────────────────────────

# Use Cloud DB if available, else fallback to local SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pet_pulse.db")

# Configure database engine
if DATABASE_URL.startswith("sqlite"):
    # SQLite requires check_same_thread=False for multiple threads
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

# Create Session factory and Base class for models
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ─── DATABASE MODELS (SQLAlchemy) ──────────────────────────────────────────────

class User(Base):
    """Stores user accounts and their associated single pet information."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String, default="pet_owner") # pet_owner, doctor, shelter, admin
    
    # Security fields
    failed_attempts = Column(Integer, default=0)
    is_locked = Column(Boolean, default=False)
    
    # Pet details stored directly on user for 1:1 relationship
    pet_name = Column(String, nullable=True)
    pet_type = Column(String, nullable=True)
    pet_age = Column(String, nullable=True)
    pet_details = Column(String, nullable=True)

class MarketplaceItem(Base):
    """Items listed for sale or adoption in the marketplace."""
    __tablename__ = "marketplace"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String); breed = Column(String); price = Column(Integer)
    seller_id = Column(Integer); seller_name = Column(String)
    status = Column(String, default="available") # available, sold

class Appointment(Base):
    """Veterinary appointments scheduled by pet owners."""
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    vet_id = Column(Integer); pet_id = Column(Integer)
    pet_name = Column(String); time = Column(String)
    status = Column(String, default="pending") # pending, completed

class ShelterAnimal(Base):
    """Animals currently in care at a shelter."""
    __tablename__ = "shelter_animals"
    id = Column(Integer, primary_key=True, index=True)
    shelter_id = Column(Integer); name = Column(String); type = Column(String)
    status = Column(String, default="In Care"); intake_date = Column(String)

class AdoptionRequest(Base):
    """Requests made by users to adopt a shelter animal."""
    __tablename__ = "adoption_requests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer); user_name = Column(String)
    pet_id = Column(Integer); pet_name = Column(String)
    shelter_id = Column(Integer); status = Column(String, default="pending")
    message = Column(String)

class MedicalRecord(Base):
    """Clinical history records for pets, usually added by vets."""
    __tablename__ = "medical_records"
    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer); date = Column(String)
    diagnosis = Column(String); treatment = Column(String); vet_name = Column(String)

class DietLog(Base):
    """Daily nutrition logs recorded by pet owners."""
    __tablename__ = "diet_logs"
    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer); food_item = Column(String)
    amount = Column(String); timestamp = Column(String)

class PanicAlert(Base):
    """Broadcast alerts for lost pets."""
    __tablename__ = "panic_alerts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer); pet_name = Column(String)
    location = Column(String); description = Column(String)
    status = Column(String, default="active") # active, resolved

class ForumPost(Base):
    """Community forum messages."""
    __tablename__ = "forum_posts"
    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String); content = Column(String); timestamp = Column(String)

class Vaccination(Base):
    """Immunization records for pets with due date tracking."""
    __tablename__ = "vaccinations"
    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer)
    vaccine_name = Column(String)
    date_administered = Column(String)
    next_due_date = Column(String)
    status = Column(String, default="Completed") # Completed, Pending, Overdue

# Initialize database tables
Base.metadata.create_all(bind=engine)

# Apply schema updates for safety features if needed
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN failed_attempts INTEGER DEFAULT 0"))
        conn.commit()
except Exception:
    pass

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_locked BOOLEAN DEFAULT 0"))
        conn.commit()
except Exception:
    pass

# Seed database with a default vet account if it doesn't exist
db = SessionLocal()
if not db.query(User).filter(User.email == "vet@petpulse.com").first():
    default_vet = User(name="Dr. PetPulse", email="vet@petpulse.com", password="vet", role="doctor")
    db.add(default_vet)
    db.commit()
db.close()

# ─── APP INITIALIZATION ───────────────────────────────────────────────────────

app = FastAPI(title="PetPulse API")

# Configure CORS to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for dev; narrow this down for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debug middleware to log all incoming requests
@app.middleware("http")
async def log_requests(request, call_next):
    print(f"DEBUG: {request.method} {request.url}")
    response = await call_next(request)
    return response

# Dependency to get a DB session for route handlers
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# ─── PYDANTIC SCHEMAS (Request/Response Validation) ───────────────────────────

class SignupRequest(BaseModel):
    name: str; email: str; password: str; role: str = "pet_owner"

class LoginRequest(BaseModel):
    email: str; password: str

class PetCreate(BaseModel):
    owner_id: int; name: str; type: str; age: str; extra_details: Optional[str] = None

class PetUpdate(BaseModel):
    name: str; type: str; age: str; extra_details: Optional[str] = None

class MarketCreate(BaseModel):
    name: str; breed: str; price: int; seller_id: int; seller_name: str

class AppointmentCreate(BaseModel):
    vet_id: int; pet_id: int; pet_name: str; time: str

class AnimalCreate(BaseModel):
    shelter_id: int; name: str; type: str; intake_date: str

class VaccinationCreate(BaseModel):
    pet_id: int; vaccine_name: str; date_administered: str; next_due_date: str; status: str = "Completed"

class VaccinationUpdate(BaseModel):
    status: str

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

# ─── AUTHENTICATION ENDPOINTS ─────────────────────────────────────────────────

@app.post("/signup")
def signup(user_data: SignupRequest, db: Session = Depends(get_db)):
    """Registers a new user."""
    if len(user_data.password) < 6 or len(user_data.password) > 20:
        raise HTTPException(400, "Password length must be between 6 and 20 characters.")
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(400, "Email already registered.")
    u = User(name=user_data.name, email=user_data.email, password=user_data.password, role=user_data.role)
    db.add(u); db.commit(); db.refresh(u)
    return {"message": "Account created!", "user": u.name, "role": u.role}

@app.post("/login")
def login(c: LoginRequest, db: Session = Depends(get_db)):
    """Authenticates a user and returns their profile info."""
    # Special bypass for hardcoded admin (legacy)
    if c.email == "Umar" and c.password == "123456":
        return {"message": "ok", "user": {"id": 9999, "name": "Umar (Admin)", "email": "admin@petpulse.com", "role": "admin"}}
    
    # Standard DB authentication
    u = db.query(User).filter(User.email == c.email).first()
    if not u:
        raise HTTPException(401, "Invalid credentials")
        
    is_locked = getattr(u, 'is_locked', False)
    if is_locked is None: is_locked = False
    
    if is_locked:
        raise HTTPException(403, "Account Locked")
        
    current_attempts = getattr(u, 'failed_attempts', 0)
    if current_attempts is None: current_attempts = 0
        
    if u.password != c.password:
        u.failed_attempts = current_attempts + 1
        if u.failed_attempts >= 6:
            u.is_locked = True
        db.commit()
        raise HTTPException(401, "Invalid credentials")
        
    # Reset failed attempts on success
    if current_attempts > 0:
        u.failed_attempts = 0
        db.commit()
        
    return {"message": "ok", "user": {"id": u.id, "name": u.name, "email": u.email, "role": u.role}}

# ─── PET MANAGEMENT ───────────────────────────────────────────────────────────

@app.get("/pets")
def get_pets(owner_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Retrieves pets for a specific owner or all pets if no owner_id provided."""
    q = db.query(User)
    if owner_id is not None:
        q = q.filter(User.id == owner_id)
    users = q.all()
    pets = []
    for u in users:
        if u.pet_name:
            pets.append({
                "id": u.id, "owner_id": u.id, "name": u.pet_name, 
                "type": u.pet_type, "age": u.pet_age, "extra_details": u.pet_details
            })
    return pets

@app.post("/pets")
def add_pet(pet: PetCreate, db: Session = Depends(get_db)):
    """Registers a pet for an existing user account."""
    try:
        age_int = int(pet.age)
        if age_int < 0 or age_int > 30:
            raise HTTPException(400, "Pet age must be between 0 and 30 years.")
    except ValueError:
        raise HTTPException(400, "Pet age must be a valid integer.")
        
    user = db.query(User).filter(User.id == pet.owner_id).first()
    if not user: raise HTTPException(404, "User not found")
    user.pet_name = pet.name; user.pet_type = pet.type; user.pet_age = pet.age; user.pet_details = pet.extra_details
    db.commit()
    return {"id": user.id, "owner_id": user.id, "name": user.pet_name, "type": user.pet_type, "age": user.pet_age, "extra_details": user.pet_details}

@app.put("/pets/{pet_id}")
def update_pet(pet_id: int, data: PetUpdate, db: Session = Depends(get_db)):
    """Updates pet information."""
    try:
        age_int = int(data.age)
        if age_int < 0 or age_int > 30:
            raise HTTPException(400, "Pet age must be between 0 and 30 years.")
    except ValueError:
        raise HTTPException(400, "Pet age must be a valid integer.")
        
    user = db.query(User).filter(User.id == pet_id).first()
    if not user or not user.pet_name: raise HTTPException(404, "Pet not found")
    user.pet_name = data.name; user.pet_type = data.type; user.pet_age = data.age; user.pet_details = data.extra_details
    db.commit()
    return {"id": user.id, "owner_id": user.id, "name": user.pet_name, "type": user.pet_type, "age": user.pet_age, "extra_details": user.pet_details}

@app.delete("/pets/{pet_id}")
def delete_pet(pet_id: int, db: Session = Depends(get_db)):
    """Removes a pet's details from a user profile."""
    user = db.query(User).filter(User.id == pet_id).first()
    if user:
        user.pet_name = None; user.pet_type = None; user.pet_age = None
        db.commit()
    return {"message": "Pet deleted"}

# ─── MARKETPLACE ENDPOINTS ────────────────────────────────────────────────────

@app.get("/marketplace")
def get_marketplace(status: Optional[str] = None, seller_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lists items for sale with optional status and seller filters."""
    q = db.query(MarketplaceItem)
    if status: q = q.filter(MarketplaceItem.status == status)
    if seller_id is not None: q = q.filter(MarketplaceItem.seller_id == seller_id)
    return q.all()

@app.post("/marketplace")
def add_marketplace(item: MarketCreate, db: Session = Depends(get_db)):
    """Adds a new item to the marketplace."""
    if item.price < 1 or item.price > 10000:
        raise HTTPException(400, "Marketplace item price must be between 1 and 10,000.")
    i = MarketplaceItem(**item.dict()); db.add(i); db.commit(); db.refresh(i); return i

@app.delete("/marketplace/{item_id}")
def delete_listing(item_id: int, db: Session = Depends(get_db)):
    """Removes a marketplace listing."""
    item = db.query(MarketplaceItem).filter(MarketplaceItem.id == item_id).first()
    if item: db.delete(item); db.commit()
    return {"message": "Listing removed"}

@app.put("/marketplace/{item_id}/buy")
def buy_item(item_id: int, buyer_id: int, db: Session = Depends(get_db)):
    """Processes a purchase and assigns the pet name to the buyer."""
    item = db.query(MarketplaceItem).filter(MarketplaceItem.id == item_id).first()
    if not item: raise HTTPException(404, "Not found")
    if item.status != "available": raise HTTPException(400, "Already sold")
    buyer = db.query(User).filter(User.id == buyer_id).first()
    if not buyer: raise HTTPException(404, "Buyer not found")
    
    item.status = "sold"
    buyer.pet_name = item.name
    buyer.pet_type = item.breed
    buyer.pet_age = "Unknown"
    db.commit()
    return {"message": "Purchase successful"}

# ─── VETERINARY SERVICES ──────────────────────────────────────────────────────

@app.get("/vet_appointments")
def get_appointments(vet_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lists all vet appointments."""
    q = db.query(Appointment)
    if vet_id is not None: q = q.filter(Appointment.vet_id == vet_id)
    return q.all()

@app.post("/vet_appointments")
def book_appointment(a: AppointmentCreate, db: Session = Depends(get_db)):
    """Schedules a new appointment with the default vet."""
    # Find the central vet account
    vet = db.query(User).filter(User.email == "vet@petpulse.com").first()
    if not vet:
        vet = User(name="Dr. PetPulse", email="vet@petpulse.com", password="vet", role="doctor")
        db.add(vet); db.commit(); db.refresh(vet)
    
    data = a.dict()
    data['vet_id'] = vet.id
    appt = Appointment(**data); db.add(appt); db.commit(); db.refresh(appt); return appt

@app.delete("/vet_appointments/{appt_id}")
def cancel_appointment(appt_id: int, db: Session = Depends(get_db)):
    """Cancels an appointment."""
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if a: db.delete(a); db.commit()
    return {"message": "Appointment cancelled"}

@app.put("/vet_appointments/{appt_id}/complete")
def complete_appointment(appt_id: int, db: Session = Depends(get_db)):
    """Marks an appointment as completed by the vet."""
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not a: raise HTTPException(404, "Not found")
    a.status = "completed"; db.commit(); return a

# ─── SHELTER & ADOPTION ───────────────────────────────────────────────────────

@app.get("/shelter_animals")
def get_shelter_animals(shelter_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lists animals currently in shelters."""
    q = db.query(ShelterAnimal)
    if shelter_id is not None: q = q.filter(ShelterAnimal.shelter_id == shelter_id)
    return q.all()

@app.post("/shelter_animals")
def add_shelter_animal(a: AnimalCreate, db: Session = Depends(get_db)):
    """Adds a new animal to a shelter registry."""
    animal = ShelterAnimal(**a.dict()); db.add(animal); db.commit(); db.refresh(animal); return animal

@app.put("/shelter_animals/{animal_id}/status")
def update_animal_status(animal_id: int, status: str, db: Session = Depends(get_db)):
    """Updates an animal's care status (e.g. In Care, Adopted)."""
    a = db.query(ShelterAnimal).filter(ShelterAnimal.id == animal_id).first()
    if not a: raise HTTPException(404, "Not found")
    a.status = status; db.commit(); return a

@app.delete("/shelter_animals/{animal_id}")
def delete_shelter_animal(animal_id: int, db: Session = Depends(get_db)):
    """Removes an animal from shelter registry."""
    a = db.query(ShelterAnimal).filter(ShelterAnimal.id == animal_id).first()
    if a: db.delete(a); db.commit()
    return {"message": "Deleted"}

@app.get("/adoption_requests")
def get_adoption_requests(shelter_id: Optional[int] = None, user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Lists adoption requests for shelters or users."""
    q = db.query(AdoptionRequest)
    if shelter_id is not None: q = q.filter(AdoptionRequest.shelter_id == shelter_id)
    if user_id is not None: q = q.filter(AdoptionRequest.user_id == user_id)
    return q.all()

@app.post("/adoption_requests")
def create_adoption_request(req: AdoptionCreate, db: Session = Depends(get_db)):
    """Submits a new adoption request."""
    r = AdoptionRequest(**req.dict()); db.add(r); db.commit(); db.refresh(r); return r

@app.put("/adoption_requests/{req_id}")
def update_adoption_status(req_id: int, status: str, db: Session = Depends(get_db)):
    """Approves or denies an adoption request."""
    r = db.query(AdoptionRequest).filter(AdoptionRequest.id == req_id).first()
    if not r: raise HTTPException(404, "Not found")
    r.status = status; db.commit(); return r

# ─── MEDICAL RECORDS & HEALTH ─────────────────────────────────────────────────

@app.get("/medical_records/{pet_id}")
def get_medical_records(pet_id: int, db: Session = Depends(get_db)):
    """Retrieves clinical history for a specific pet."""
    return db.query(MedicalRecord).filter(MedicalRecord.pet_id == pet_id).all()

@app.post("/medical_records")
def add_medical_record(rec: MedicalCreate, db: Session = Depends(get_db)):
    """Adds a new clinical record to a pet's history."""
    r = MedicalRecord(**rec.dict()); db.add(r); db.commit(); db.refresh(r); return r

@app.delete("/medical_records/{rec_id}")
def delete_medical_record(rec_id: int, db: Session = Depends(get_db)):
    """Removes a medical record entry."""
    r = db.query(MedicalRecord).filter(MedicalRecord.id == rec_id).first()
    if r: db.delete(r); db.commit()
    return {"message": "Deleted"}

@app.get("/vaccinations/{pet_id}")
def get_vaccinations(pet_id: int, db: Session = Depends(get_db)):
    """Lists immunizations for a pet."""
    return db.query(Vaccination).filter(Vaccination.pet_id == pet_id).all()

@app.post("/vaccinations")
def add_vaccination(v: VaccinationCreate, db: Session = Depends(get_db)):
    """Logs a new vaccination shot."""
    vacc = Vaccination(**v.dict()); db.add(vacc); db.commit(); db.refresh(vacc); return vacc

@app.put("/vaccinations/{vacc_id}")
def update_vaccination(vacc_id: int, data: VaccinationUpdate, db: Session = Depends(get_db)):
    """Changes immunization status (Completed, Pending, etc.)."""
    v = db.query(Vaccination).filter(Vaccination.id == vacc_id).first()
    if not v: raise HTTPException(404, "Not found")
    v.status = data.status; db.commit(); return v

# ─── LIFESTYLE & SOCIAL ───────────────────────────────────────────────────────

@app.get("/diet_logs/{pet_id}")
def get_diet_logs(pet_id: int, db: Session = Depends(get_db)):
    """Retrieves nutrition logs for a pet."""
    return db.query(DietLog).filter(DietLog.pet_id == pet_id).all()

@app.post("/diet_logs")
def add_diet_log(log: DietCreate, db: Session = Depends(get_db)):
    """Adds a daily nutrition entry."""
    l = DietLog(**log.dict()); db.add(l); db.commit(); db.refresh(l); return l

@app.get("/panic_alerts")
def get_panic_alerts(db: Session = Depends(get_db)):
    """Retrieves active 'Lost Pet' alerts."""
    return db.query(PanicAlert).filter(PanicAlert.status == "active").all()

@app.post("/panic_alerts")
def create_panic_alert(a: PanicCreate, db: Session = Depends(get_db)):
    """Broadcasts a new panic alert."""
    alert = PanicAlert(**a.dict()); db.add(alert); db.commit(); db.refresh(alert); return alert

@app.get("/forum_posts")
def get_forum_posts(db: Session = Depends(get_db)):
    """Retrieves all community forum messages."""
    return db.query(ForumPost).order_by(ForumPost.id.asc()).all()

@app.post("/forum_posts")
def add_forum_post(post: ForumCreate, db: Session = Depends(get_db)):
    """Adds a new message to the forum."""
    p = ForumPost(**post.dict()); db.add(p); db.commit(); db.refresh(p); return p

# ─── AI CHATBOT (LM Studio - Local) ───────────────────────────────────────────

# Configure client to talk to local LM Studio server
ai_client = OpenAI(
    base_url="http://127.0.0.1:1234/v1",
    api_key="lm-studio" # Dummy key
)

@app.post("/api/ai/chat")
def api_chat_with_ai(req: ChatRequest):
    """Processes user questions via local AI (Gemma 4B)."""
    print("\n" + "="*50)
    print("🔥 AI CHAT REQUEST RECEIVED (POST) 🔥")
    print(f"Message: {req.message}")
    print("="*50)
    
    try:
        user_message = req.message
        # Prepend pet info if available for better context
        if req.pet_info:
            user_message = f"Pet Info: {req.pet_info}\n\nUser Question: {user_message}"

        # Call local model
        response = ai_client.chat.completions.create(
            model="gemma-4",
            messages=[
                {"role": "system", "content": "You are Gemma 4, a helpful pet nutrition expert assistant."},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=250
        )

        reply = response.choices[0].message.content
        return {"reply": reply.strip()}
    except Exception as e:
        print(f"❌ AI ERROR: {e}")
        return {"reply": f"AI error: {str(e)}"}

# ─── ADMINISTRATION ───────────────────────────────────────────────────────────

@app.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    """Returns all registered user accounts (Admin only)."""
    return db.query(User).all()

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Permanently removes a user account."""
    u = db.query(User).filter(User.id == user_id).first()
    if u: db.delete(u); db.commit()
    return {"message": "User removed"}

@app.get("/admin/stats")
def get_admin_stats(db: Session = Depends(get_db)):
    """Provides platform-wide metrics for the Admin Dashboard."""
    return {
        "users": db.query(User).count(),
        "vets": db.query(User).filter(User.role == "doctor").count(),
        "shelters": db.query(User).filter(User.role == "shelter").count(),
        "pets": db.query(User).filter(User.pet_name != None).count(),
        "marketplace": db.query(MarketplaceItem).count(),
        "appointments": db.query(Appointment).count(),
        "alerts": db.query(PanicAlert).filter(PanicAlert.status == "active").count(),
        "forum_posts": db.query(ForumPost).count(),
    }

# ─── CATCH-ALL & STARTUP ──────────────────────────────────────────────────────

@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(path_name: str):
    """Fallback handler for non-existent routes."""
    print(f"DEBUG: Unmatched request to /{path_name}")
    return {"message": "Endpoint not found", "path": path_name}

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)