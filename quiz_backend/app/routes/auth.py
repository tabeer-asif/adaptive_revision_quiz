from fastapi import APIRouter, HTTPException, Header
from app.supabase_client import supabase_auth, supabase_db

router = APIRouter()

@router.post("/register")
def register(user: dict):
    email = user.get("email")
    password = user.get("password")
    first_name = user.get("first_name", "")
    surname = user.get("surname", "")
    full_name = f"{first_name} {surname}".strip()
    role = user.get("role", "student")  # default role

    # 1️⃣ Sign up user in Supabase Auth
    res = supabase_auth.auth.sign_up({
        "email": email,
        "password": password
    })

    if res.user is None:
        raise HTTPException(status_code=400, detail="Registration failed")

    user_id = res.user.id  # UUID from Supabase Auth

    try:
        # 2️⃣ Insert user into `users` table
        supabase_db.table("users").insert({
            "id": user_id,
            "email": email,
            "name": full_name,
            "role": role
        }).execute()
    except Exception as e:
        print("DB INSERT ERROR:", str(e))
        raise HTTPException(status_code=500, detail="Failed to create user record")

    return {"message": "User registered successfully", "user_id": user_id}


@router.post("/login")
def login(user: dict):
    try:
        res = supabase_auth.auth.sign_in_with_password({
            "email": user["email"],
            "password": user["password"]
        })

        return {
            "access_token": res.session.access_token,
            "user_id": res.user.id
        }

    except Exception as e:
        print("LOGIN ERROR:", str(e))
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

@router.get("/verify-token")
def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    token = authorization.split(" ")[1]
    try:
        user_resp = supabase_auth.auth.get_user(token)
        if user_resp.user is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"user_id": user_resp.user.id}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")