from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse  # <--- حطيه هنا مع الباقي
from pydantic import BaseModel
import psycopg2
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = FastAPI()

# إعداد الـ CORS للتأكد من ربط السيرفر بالواجهة بسلاسة
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# بيانات الاتصال بقاعدة بيانات Supabase أونلاين
DATABASE_URL = "postgresql://postgres.itpfvgggvxhfioxgkepl:bosy12$5F77@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"

# إعدادات البريد الإلكتروني الخاص بكِ (الإيميل المرسِل الجديد)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "basmallay30@gmail.com" 
SENDER_PASSWORD = "fvfx sfga bplv unhv" 

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# Pydantic Schemas
class LoginRequest(BaseModel):
    user_code: str

class TaskCreate(BaseModel):
    title: str
    description: str = None
    deadline: str
    priority: str
    assigned_to: int  # الـ user_id الخاص بالعضو المسؤول عن التاسك

class SubmissionCreate(BaseModel):
    task_id: int
    user_id: int
    content: str

# دالة إرسال الإيميل من بريدك الشخصي
def send_email_to_user(to_email: str, task_title: str, deadline: str, description: str):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"TaskFlow: New Task Assigned - {task_title}"

        body = f"""
        Hello,
        
        You have been assigned a new task in TaskFlow Project Management Portal:
        
        Task: {task_title}
        Description: {description}
        Deadline: {deadline}
        
        Please log in to the portal to check and submit your work.
        
        Best regards,
        TaskFlow Team
        """
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        print("EMAIL SENT SUCCESSFULLY!")
    except Exception as e:
        print(f"❌ DETAILED SMTP ERROR: {str(e)}")
        raise e

# Endpoints
@app.get("/")
def read_root():
    return FileResponse("index.html")
@app.post("/login")
def login(data: LoginRequest):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, role, user_code FROM users WHERE user_code = %s", (data.user_code.strip(),))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "status": "success",
                "user": {
                    "user_id": row[0],
                    "username": row[1],
                    "role": row[2],
                    "user_code": row[3]
                }
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid invitation code.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/")
def get_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, user_code, role, email, created_at FROM users")
    rows = cursor.fetchall()
    users_list = []
    for row in rows:
        users_list.append({
            "user_id": row[0],
            "name": row[1],
            "user_code": row[2],
            "role": row[3],
            "email": row[4],
            "created_at": str(row[5]) if row[5] else None
        })
    conn.close()
    return users_list

@app.get("/tasks/")
def get_tasks(user_id: int = None, role: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if role in ["Leader", "Supervisor"] or not user_id:
        cursor.execute("""
            SELECT t.task_id, t.title, t.description, t.priority, t.deadline, t.status, t.assigned_to, u.name 
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to = u.user_id
        """)
    else:
        cursor.execute("""
            SELECT t.task_id, t.title, t.description, t.priority, t.deadline, t.status, t.assigned_to, u.name 
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to = u.user_id
            WHERE t.assigned_to = %s
        """, (user_id,))
        
    rows = cursor.fetchall()
    tasks_list = []
    for row in rows:
        tasks_list.append({
            "task_id": row[0],
            "title": row[1],
            "description": row[2],
            "priority": row[3],
            "deadline": str(row[4]) if row[4] else None,
            "status": row[5],
            "assigned_to": row[6],
            "assigned_to_name": row[7]
        })
    conn.close()
    return tasks_list

@app.post("/tasks/")
def create_task(task: TaskCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # حفظ التاسك في قاعدة البيانات
    cursor.execute(
        "INSERT INTO tasks (title, description, priority, deadline, status, assigned_to) VALUES (%s, %s, %s, %s, 'Pending', %s) RETURNING task_id",
        (task.title, task.description, task.priority, task.deadline, task.assigned_to)
    )
    task_id = cursor.fetchone()[0]
    
    # جلب إيميل العضو المسؤول
    cursor.execute("SELECT email, name FROM users WHERE user_id = %s", (task.assigned_to,))
    user_row = cursor.fetchone()
    
    conn.commit()
    conn.close()

    # إرسال الإيميل بشكل آمن من بريدك الشخصي
    try:
        if user_row and user_row[0]:
            user_email = user_row[0]
            send_email_to_user(user_email, task.title, task.deadline, task.description)
    except Exception as mail_err:
        print(f"⚠️ Email warning (Task created successfully anyway): {mail_err}")

    return {"status": "success", "message": "Task created and email notification processed successfully"}

@app.get("/stats/")
def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM tasks")
    total_tasks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'Pending'")
    pending_tasks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'Completed'")
    completed_tasks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_tasks": total_tasks,
        "pending_tasks": pending_tasks,
        "completed_tasks": completed_tasks,
        "total_users": total_users
    }

@app.post("/submissions/")
def create_submission(sub: SubmissionCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO submissions (task_id, user_id, content) VALUES (%s, %s, %s)",
        (sub.task_id, sub.user_id, sub.content)
    )
    cursor.execute(
        "UPDATE tasks SET status = 'Completed' WHERE task_id = %s",
        (sub.task_id,)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Deliverable submitted successfully"}

@app.get("/submissions/")
def get_submissions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.submission_id, t.title, u.name, s.content, s.submitted_at 
        FROM submissions s
        JOIN tasks t ON s.task_id = t.task_id
        JOIN users u ON s.user_id = u.user_id
        ORDER BY s.submitted_at DESC
    """)
    rows = cursor.fetchall()
    subs_list = []
    for row in rows:
        subs_list.append({
            "submission_id": row[0],
            "task_title": row[1],
            "user_name": row[2],
            "content": row[3],
            "submitted_at": str(row[4]) if row[4] else None
        })
    conn.close()
    return subs_list
