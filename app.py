
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlparse
from sqlalchemy import inspect
import csv
import io

from flask import (
    Flask, render_template, render_template_string, request,
    redirect, url_for, flash, make_response
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
# 1. CONFIGURATION
# =========================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = "replace-this-with-a-long-random-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///placement.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


# =========================================================
# 2. DATABASE TABLES AND MODELS
# =========================================================

drive_departments = db.Table(
    "drive_departments",
    db.Column("drive_id", db.Integer, db.ForeignKey("drive.id"),
              primary_key=True),
    db.Column("department_id", db.Integer,
              db.ForeignKey("department.id"), primary_key=True)
)


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    department_id = db.Column(
        db.Integer, db.ForeignKey("department.id"), nullable=False
    )
    program = db.Column(db.String(100), default="B.Tech")
    year = db.Column(db.Integer, default=2)
    section = db.Column(db.String(10), default="A")
    batch = db.Column(db.String(30), default="2025-2029")
    email = db.Column(db.String(150), unique=True, nullable=False)
    registration_status = db.Column(db.String(30), default="Registered")
    cgpa = db.Column(db.Float, default=0.0)
    backlogs = db.Column(db.Integer, default=0)
    
    # Student fee details
    total_fee = db.Column(db.Float, nullable=False, default=0.0)
    fee_paid = db.Column(db.Float, nullable=False, default=0.0)
    fee_verified = db.Column(db.Boolean, nullable=False, default=False)     

    # NEW: Networking profile fields
    bio = db.Column(db.String(500), default="")
    skills = db.Column(db.String(500), default="")
    linkedin_url = db.Column(db.String(300), default="")
    github_url = db.Column(db.String(300), default="")
    portfolio_url = db.Column(db.String(300), default="")

    department = db.relationship("Department", backref="students")
    


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"),
        unique=True, nullable=True
    )
    student = db.relationship("Student", backref="user_account")


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    website = db.Column(db.String(250))


class Drive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey("company.id"), nullable=False
    )
    role = db.Column(db.String(150), nullable=False)
    package_lpa = db.Column(db.Float, default=0.0)
    location = db.Column(db.String(150))
    min_cgpa = db.Column(db.Float, default=0.0)
    max_backlogs = db.Column(db.Integer, default=0)
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), default="Open")
    company = db.relationship("Company", backref="drives")
    eligible_departments = db.relationship(
        "Department", secondary=drive_departments,
        backref="placement_drives"
    )


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"), nullable=False
    )
    drive_id = db.Column(
        db.Integer, db.ForeignKey("drive.id"), nullable=False
    )
    stage = db.Column(db.String(50), default="Applied")
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    student = db.relationship("Student", backref="applications")
    drive = db.relationship("Drive", backref="applications")
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "drive_id",
            name="unique_student_drive_application"
        ),
    )


class ClearanceCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    mandatory = db.Column(db.Boolean, default=True)


class StudentClearance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"), nullable=False
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey("clearance_category.id"), nullable=False
    )
    status = db.Column(db.String(30), default="Pending")
    remarks = db.Column(db.String(250), default="")
    student = db.relationship("Student", backref="clearances")
    category = db.relationship(
        "ClearanceCategory", backref="student_clearances"
    )
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "category_id",
            name="unique_student_clearance_category"
        ),
    )


# =========================================================
# 3. SAFE DATABASE MIGRATION FOR PROFILE FIELDS
# =========================================================

def migrate_student_profile_fields():
    if not inspect(db.engine).has_table("student"):
        return

    columns = {
        column["name"]
        for column in inspect(db.engine).get_columns("student")
    }

    new_columns = {
        "total_fee": "FLOAT DEFAULT 0.0",
        "fee_paid": "FLOAT DEFAULT 0.0",
        "fee_verified": "BOOLEAN DEFAULT 0",
        "bio": "VARCHAR(500) DEFAULT ''",
        "skills": "VARCHAR(500) DEFAULT ''",
        "linkedin_url": "VARCHAR(300) DEFAULT ''",
        "github_url": "VARCHAR(300) DEFAULT ''",
        "portfolio_url": "VARCHAR(300) DEFAULT ''",
    }

    with db.engine.begin() as connection:
        for name, sql_type in new_columns.items():
            if name not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE student ADD COLUMN {name} {sql_type}"
                )


# =========================================================
# 4. LOGIN AND ROLE PROTECTION
# =========================================================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(view_function):
    @wraps(view_function)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            return "Access denied: administrators only.", 403
        return view_function(*args, **kwargs)
    return wrapper


def student_required(view_function):
    @wraps(view_function)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "student":
            return "Access denied: students only.", 403
        return view_function(*args, **kwargs)
    return wrapper


# =========================================================
# 5. DEMO DATA
# =========================================================

def seed_demo_data():
    if Department.query.first():
        return

    departments = [
        Department(name="Information Technology", code="IT"),
        Department(name="Computer Science", code="CSE"),
        Department(name="Electronics and Communication", code="ECE"),
    ]
    db.session.add_all(departments)
    db.session.flush()

    for i in range(1, 31):
        department = departments[(i - 1) % len(departments)]
        db.session.add(Student(
            roll_number=f"DEMO{i:03d}",
            full_name=f"Demo Student {i}",
            department_id=department.id,
            program="B.Tech",
            year=2,
            section="A",
            batch="2025-2029",
            email=f"demo{i:03d}@example.com",
            cgpa=round(6.0 + (i % 40) / 10, 2),
            backlogs=0 if i % 4 else 1,
        ))

    companies = [
        Company(name="Tech Solutions", website="https://example.com"),
        Company(name="Global Systems", website="https://example.com"),
        Company(name="Digital Innovations", website="https://example.com"),
        Company(name="Cloud Services", website="https://example.com"),
        Company(name="Software Works", website="https://example.com"),
    ]
    db.session.add_all(companies)
    db.session.flush()

    roles = [
        "Software Engineer", "Web Developer", "Data Analyst",
        "Cloud Engineer", "Python Developer"
    ]

    for i, company in enumerate(companies):
        drive = Drive(
            company_id=company.id,
            role=roles[i],
            package_lpa=4.0 + i,
            location="India",
            min_cgpa=6.0,
            max_backlogs=0,
            deadline=date(2027, 12, 31),
            status="Open",
        )
        drive.eligible_departments = departments
        db.session.add(drive)

    categories = [
        ClearanceCategory(name="Library"),
        ClearanceCategory(name="Laboratory"),
        ClearanceCategory(name="Department"),
        ClearanceCategory(name="Accounts"),
    ]
    db.session.add_all(categories)
    db.session.flush()

    for student in Student.query.all():
        for category in categories:
            db.session.add(StudentClearance(
                student_id=student.id,
                category_id=category.id,
                status="Pending",
                remarks=""
            ))

    drives = Drive.query.all()
    for student in Student.query.order_by(Student.id).limit(20).all():
        if drives:
            db.session.add(Application(
                student_id=student.id,
                drive_id=drives[(student.id - 1) % len(drives)].id,
                stage="Applied"
            ))

    db.session.commit()


def seed_login_accounts():
    admin_email = "admin@university.local"

    if not User.query.filter_by(username=admin_email).first():
        db.session.add(User(
            username=admin_email,
            password_hash=generate_password_hash("AdminDemo@123"),
            role="admin"
        ))

    student = Student.query.filter_by(email="demo001@example.com").first()
    if student and not User.query.filter_by(username=student.email).first():
        db.session.add(User(
            username=student.email,
            password_hash=generate_password_hash("StudentDemo@123"),
            role="student",
            student_id=student.id
        ))

    db.session.commit()


# =========================================================
# 6. SHARED PAGE LAYOUT
# =========================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} - Placement Portal</title>
<style>
:root {
    --navy:#10243e; --blue:#2563eb; --light:#f4f7fb;
    --text:#172b4d; --border:#e2e8f0;
}
* { box-sizing:border-box; }
body {
    font-family:Arial,sans-serif; margin:0; background:var(--light);
    color:var(--text); animation:pageEnter .45s ease-out;
}
@keyframes pageEnter {
    from { opacity:0; transform:translateY(10px); }
    to { opacity:1; transform:translateY(0); }
}
header { background:var(--navy); color:white; padding:18px 5%; }
header h2 { margin:0 0 12px; }
nav { display:flex; flex-wrap:wrap; gap:8px; }
nav a { color:white; text-decoration:none; padding:8px 10px;
        border-radius:6px; transition:background .2s,transform .2s; }
nav a:hover { background:#193653; transform:translateY(-2px); }
main {
    max-width:1150px; margin:25px auto; padding:24px;
    background:white; border-radius:12px;
    box-shadow:0 5px 22px #10243e12;
}
h1 { color:var(--navy); }
input,select,textarea {
    padding:10px; margin:5px 0; max-width:100%;
    border:1px solid #cbd5e1; border-radius:6px;
}
input:focus,select:focus,textarea:focus {
    outline:2px solid #bfdbfe; border-color:var(--blue);
}
textarea { width:100%; min-height:100px; }
button,.button {
    display:inline-block; background:var(--blue); color:white;
    border:0; border-radius:6px; padding:10px 15px;
    cursor:pointer; text-decoration:none;
    transition:transform .2s,box-shadow .2s;
}
button:hover,.button:hover {
    transform:translateY(-2px);
    box-shadow:0 5px 14px #2563eb35;
}
table { border-collapse:collapse; width:100%; margin-top:15px; }
th,td { border:1px solid var(--border); padding:10px; text-align:left; }
th { background:#e8eefc; }
tr { transition:background .2s; }
tbody tr:hover,tr:hover { background:#f4f8ff; }
.message { background:#fff4cc; padding:12px; margin-bottom:12px;
           border-radius:6px; }
.cards { display:flex; gap:15px; flex-wrap:wrap; margin:20px 0; }
.card {
    padding:18px; background:#f0f5ff; border:1px solid var(--border);
    border-radius:10px; min-width:140px; flex:1;
    animation:pageEnter .6s ease-out both;
    transition:transform .25s,box-shadow .25s;
}
.card:hover { transform:translateY(-5px); box-shadow:0 8px 22px #10243e18; }
.profile-header {
    background:linear-gradient(120deg,#10243e,#2563eb,#193653);
    background-size:200% 200%; color:white; padding:25px;
    border-radius:12px; animation:gradientMove 8s ease infinite;
}
.profile-header h1 { color:white; }
@keyframes gradientMove {
    0%,100% { background-position:0% 50%; }
    50% { background-position:100% 50%; }
}
.profile-links { display:flex; gap:10px; flex-wrap:wrap; }
.profile-links a { margin:5px 0; }
.placement-marquee {
    overflow:hidden; background:var(--navy); color:white;
    padding:17px 0; margin-top:30px; border-top:3px solid var(--blue);
}
.marquee-track {
    display:flex; width:max-content; gap:35px; white-space:nowrap;
    animation:trainingScroll 22s linear infinite;
}
.marquee-track span { font-weight:bold; font-size:20px; letter-spacing:1px; }
@keyframes trainingScroll {
    from { transform:translateX(0); }
    to { transform:translateX(-50%); }
}
.placement-marquee:hover .marquee-track { animation-play-state:paused; }
@media(max-width:700px) {
    main { margin:12px; padding:15px; overflow-x:auto; }
    table { font-size:12px; }
}
@media(prefers-reduced-motion:reduce) {
    *,*::before,*::after { animation:none !important; transition:none !important; }
}
</style>
</head>
<body>
<header>
    <h2>University Placement & No-Dues Portal</h2>
    <nav>
        <a href="{{ url_for('home') }}">Home</a>
        {% if current_user.is_authenticated %}
            {% if current_user.role == 'admin' %}
                <a href="{{ url_for('admin_dashboard') }}">Admin Dashboard</a>
                <a href="{{ url_for('students_page') }}">Students</a>
                <a href="{{ url_for('companies_page') }}">Companies</a>
                <a href="{{ url_for('drives_page') }}">Placement Drives</a>
                <a href="{{ url_for('applications_page') }}">Applications</a>
                <a href="{{ url_for('clearances_page') }}">No-Dues</a>
                <a href="{{ url_for('admin_cgpa_selection') }}">CGPA Selection</a>
            {% else %}
                <a href="{{ url_for('student_dashboard') }}">My Dashboard</a>
                {% if current_user.student_id %}
                <a href="{{ url_for('student_profile',
                     student_id=current_user.student_id) }}">My Profile</a>
                {% endif %}
            {% endif %}
            <a href="{{ url_for('logout') }}">Logout</a>
        {% else %}
            <a href="{{ url_for('login') }}">Login</a>
        {% endif %}
    </nav>
</header>
<main>
    {% with messages = get_flashed_messages() %}
        {% for message in messages %}
            <div class="message">{{ message }}</div>
        {% endfor %}
    {% endwith %}
    PAGE_CONTENT
    <section class="placement-marquee" aria-label="Placement Training">
        <div class="marquee-track">
            <span>PLACEMENT TRAINING</span><span>✦</span>
            <span>BUILD YOUR CAREER</span><span>✦</span>
            <span>INTERVIEW PREPARATION</span><span>✦</span>
            <span>PLACEMENT TRAINING</span><span>✦</span>
            <span>BUILD YOUR CAREER</span><span>✦</span>
            <span>INTERVIEW PREPARATION</span><span>✦</span>
        </div>
    </section>
</main>
</body>
</html>
"""


def page(title, content, **context):
    return render_template_string(
        BASE_HTML.replace("PAGE_CONTENT", content),
        title=title,
        **context
    )


# =========================================================
# 7. HOME AND AUTHENTICATION
# =========================================================

@app.route("/")
def home():
    content = """
    <h1>University Placement Portal</h1>
    <p>Manage placements, student networking and departmental No-Dues.</p>
    <div class="cards">
      <div class="card"><h3>Students</h3><h2>{{ student_count }}</h2></div>
      <div class="card"><h3>Companies</h3><h2>{{ company_count }}</h2></div>
      <div class="card"><h3>Placement Drives</h3><h2>{{ drive_count }}</h2></div>
      <div class="card"><h3>Applications</h3><h2>{{ application_count }}</h2></div>
    </div>
    {% if not current_user.is_authenticated %}
      <a class="button" href="{{ url_for('login') }}">Login to continue</a>
    {% endif %}
    """
    return page(
        "Home", content,
        student_count=Student.query.count(),
        company_count=Company.query.count(),
        drive_count=Drive.query.count(),
        application_count=Application.query.count()
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password.")

    content = """
    <h1>Login</h1>
    <form method="POST">
      <label>Email address</label><br>
      <input type="email" name="email" required><br>
      <label>Password</label><br>
      <input type="password" name="password" required><br>
      <button type="submit">Login</button>
    </form>
    <hr>
    <p>Demo admin: admin@university.local</p>
    <p>Demo student: demo001@example.com</p>
    <p>Admin password: AdminDemo@123</p>
    <p>Student password: StudentDemo@123</p>
    """
    return page("Login", content)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for("login"))


# =========================================================
# 8. ADMIN DASHBOARD
# =========================================================

@app.route("/admin-dashboard")
@admin_required
def admin_dashboard():
    content = """
    <h1>Administrator Dashboard</h1>
    <p>Welcome, {{ current_user.username }}</p>
    <div class="cards">
      <div class="card"><h3>Students</h3><h2>{{ students }}</h2></div>
      <div class="card"><h3>Companies</h3><h2>{{ companies }}</h2></div>
      <div class="card"><h3>Drives</h3><h2>{{ drives }}</h2></div>
      <div class="card"><h3>Applications</h3><h2>{{ applications }}</h2></div>
      <div class="card"><h3>Selected</h3><h2>{{ selected }}</h2></div>
      <div class="card"><h3>Pending No-Dues</h3><h2>{{ pending }}</h2></div>
    </div>
    <p><a href="{{ url_for('export_students') }}">Export students as CSV</a></p>
    <p><a href="{{ url_for('db_check') }}">Database check</a></p>
    """
    return page(
        "Admin Dashboard", content,
        students=Student.query.count(),
        companies=Company.query.count(),
        drives=Drive.query.count(),
        applications=Application.query.count(),
        selected=Application.query.filter_by(stage="Selected").count(),
        pending=StudentClearance.query.filter(
            StudentClearance.status != "Cleared"
        ).count()
    )


# =========================================================
# 9. STUDENT DASHBOARD
# =========================================================

def is_student_eligible(student, drive):
    return (
        student.cgpa >= drive.min_cgpa
        and student.backlogs <= drive.max_backlogs
        and student.department in drive.eligible_departments
        and drive.status == "Open"
        and (drive.deadline is None or drive.deadline >= date.today())
    )


@app.route("/student-dashboard")
@student_required
def student_dashboard():
    student = db.session.get(Student, current_user.student_id)
    if student is None:
        return "Your account is not linked to a student record.", 400

    applications = Application.query.filter_by(student_id=student.id).all()
    clearances = StudentClearance.query.filter_by(student_id=student.id).all()
    drives = Drive.query.order_by(Drive.id.desc()).all()

    content = """
    <h1>Student Dashboard</h1>
    <p>Welcome, {{ student.full_name }}!</p>
    <p><a class="button" href="{{ url_for('student_profile',
        student_id=student.id) }}">View My Profile</a>
       <a class="button" href="{{ url_for('edit_my_profile',
        student_id=student.id) }}">Edit My Profile</a></p>

    <h3>Student Details</h3>
    <p>Roll number: {{ student.roll_number }}</p>
    <p>Email: {{ student.email }}</p>
    <p>Department: {{ student.department.name }}</p>
    <p>CGPA: {{ student.cgpa }}</p>
    <p>Backlogs: {{ student.backlogs }}</p>

    <h3>Available Placement Drives</h3>
    <table>
      <tr><th>Company</th><th>Role</th><th>Package (LPA)</th>
          <th>Eligibility</th><th>Action</th></tr>
      {% for drive in drives %}
      <tr>
        <td>{{ drive.company.name }}</td><td>{{ drive.role }}</td>
        <td>{{ drive.package_lpa }}</td>
        <td>{{ 'Eligible' if is_eligible(drive) else 'Not eligible / Closed' }}</td>
        <td>
        {% if is_eligible(drive) and drive.id not in applied_drive_ids %}
          <form method="POST" action="{{ url_for('apply_drive',
               drive_id=drive.id) }}"><button>Apply</button></form>
        {% elif drive.id in applied_drive_ids %}Already applied
        {% else %}Not available{% endif %}
        </td>
      </tr>
      {% else %}
      <tr><td colspan="5">No drives available.</td></tr>
      {% endfor %}
    </table>

    <h3>My Applications</h3>
    <table><tr><th>Company</th><th>Role</th><th>Stage</th></tr>
    {% for application in applications %}
      <tr><td>{{ application.drive.company.name }}</td>
          <td>{{ application.drive.role }}</td><td>{{ application.stage }}</td></tr>
    {% else %}<tr><td colspan="3">No applications yet.</td></tr>{% endfor %}
    </table>

    <h3>My No-Dues Status</h3>
    <table><tr><th>Category</th><th>Status</th><th>Remarks</th></tr>
    {% for clearance in clearances %}
      <tr><td>{{ clearance.category.name }}</td><td>{{ clearance.status }}</td>
          <td>{{ clearance.remarks or '-' }}</td></tr>
    {% else %}<tr><td colspan="3">No clearance records.</td></tr>{% endfor %}
    </table>
    <p>Overall No-Dues: <strong>{{ overall_status }}</strong></p>
    """
    overall_status = (
        "Cleared"
        if clearances and all(c.status == "Cleared" for c in clearances)
        else "Pending"
    )
    return page(
        "Student Dashboard", content,
        student=student, drives=drives, applications=applications,
        clearances=clearances,
        applied_drive_ids={a.drive_id for a in applications},
        overall_status=overall_status,
        is_eligible=lambda drive: is_student_eligible(student, drive)
    )


# =========================================================
# 10. STUDENT MANAGEMENT
# =========================================================

@app.route("/students", methods=["GET", "POST"])
@admin_required
def students_page():
    message = None

    if request.method == "POST":
        try:
            roll_number = request.form.get("roll_number", "").strip()
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            department_id = int(request.form.get("department_id", "0"))
            cgpa = float(request.form.get("cgpa", "0"))
            backlogs = int(request.form.get("backlogs", "0"))
            year = int(request.form.get("year", "2"))

            if not roll_number or not full_name or not email:
                raise ValueError("Roll number, name and email are required.")
            if not 0 <= cgpa <= 10 or backlogs < 0 or year < 1:
                raise ValueError("Enter valid CGPA, backlog and year values.")
            if not db.session.get(Department, department_id):
                raise ValueError("Select a valid department.")
            if Student.query.filter(
                db.or_(Student.roll_number == roll_number,
                       Student.email == email)
            ).first():
                raise ValueError("Roll number or email already exists.")

            student = Student(
                roll_number=roll_number, full_name=full_name,
                email=email, department_id=department_id,
                cgpa=cgpa, backlogs=backlogs, year=year,
                program="B.Tech", section="A", batch="2025-2029",
                registration_status="Registered"
            )
            db.session.add(student)
            db.session.commit()
            flash("Student added successfully.")
            return redirect(url_for("students_page"))
        except ValueError as error:
            db.session.rollback()
            message = str(error)

    search = request.args.get("q", "").strip()
    query = Student.query
    if search:
        query = query.filter(db.or_(
            Student.full_name.ilike(f"%{search}%"),
            Student.roll_number.ilike(f"%{search}%"),
            Student.email.ilike(f"%{search}%")
        ))
    students = query.order_by(Student.roll_number).all()

    content = """
    <h1>Student Management</h1>
    {% if message %}<div class="message">{{ message }}</div>{% endif %}
    <h3>Add Student</h3>
    <form method="POST">
      <input name="roll_number" placeholder="Roll number" required>
      <input name="full_name" placeholder="Full name" required>
      <input type="email" name="email" placeholder="Email" required>
      <select name="department_id" required>
        <option value="">Select department</option>
        {% for department in departments %}
        <option value="{{ department.id }}">{{ department.name }}</option>
        {% endfor %}
      </select>
      <input type="number" name="cgpa" placeholder="CGPA" min="0" max="10"
             step="0.01" required>
      <input type="number" name="backlogs" placeholder="Backlogs"
             min="0" value="0" required>
      <input type="number" name="year" placeholder="Year" min="1" max="6"
             value="2" required>
      <button>Add Student</button>
    </form>

    <h3>Search Students</h3>
    <form method="GET">
      <input name="q" value="{{ search }}"
             placeholder="Name, roll number or email">
      <button>Search</button>
      <a href="{{ url_for('students_page') }}">Clear</a>
    </form>

    <table>
      <tr><th>Roll No.</th><th>Name</th><th>Email</th><th>Department</th>
          <th>CGPA</th><th>Backlogs</th><th>Profile</th><th>Edit</th></tr>
      {% for student in students %}
      <tr>
        <td>{{ student.roll_number }}</td>
        <td><a href="{{ url_for('student_profile',
              student_id=student.id) }}">{{ student.full_name }}</a></td>
        <td>{{ student.email }}</td><td>{{ student.department.name }}</td>
        <td>{{ student.cgpa }}</td><td>{{ student.backlogs }}</td>
        <td><a href="{{ url_for('student_profile',
              student_id=student.id) }}">View Profile</a></td>
        <td><a href="{{ url_for('edit_student',
              student_id=student.id) }}">Edit</a></td>
      </tr>
      {% else %}<tr><td colspan="8">No students found.</td></tr>{% endfor %}
    </table>
    <p><a href="{{ url_for('export_students') }}">Export student data to CSV</a></p>
    """
    return page(
        "Students", content, students=students,
        departments=Department.query.order_by(Department.name).all(),
        search=search, message=message
    )


@app.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
@admin_required
def edit_student(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return "Student not found.", 404

    if request.method == "POST":
        try:
            name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            department_id = int(request.form.get("department_id", "0"))
            cgpa = float(request.form.get("cgpa", "0"))
            backlogs = int(request.form.get("backlogs", "0"))

            if not name or not email:
                raise ValueError("Name and email are required.")
            if not 0 <= cgpa <= 10 or backlogs < 0:
                raise ValueError("Enter valid CGPA and backlog values.")
            if not db.session.get(Department, department_id):
                raise ValueError("Select a valid department.")
            if Student.query.filter(
                Student.id != student.id, Student.email == email
            ).first():
                raise ValueError("That email address is already in use.")

            student.full_name = name
            student.email = email
            student.department_id = department_id
            student.cgpa = cgpa
            student.backlogs = backlogs
            db.session.commit()
            flash("Student updated successfully.")
            return redirect(url_for("students_page"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error))

    content = """
    <h1>Edit Student</h1>
    <form method="POST">
      <p>Roll number: <strong>{{ student.roll_number }}</strong></p>
      <label>Full name</label><br>
      <input name="full_name" value="{{ student.full_name }}" required><br>
      <label>Email</label><br>
      <input type="email" name="email" value="{{ student.email }}" required><br>
      <label>Department</label><br>
      <select name="department_id" required>
        {% for department in departments %}
        <option value="{{ department.id }}"
          {% if department.id == student.department_id %}selected{% endif %}>
          {{ department.name }}
        </option>
        {% endfor %}
      </select><br>
      <label>CGPA</label><br>
      <input type="number" name="cgpa" min="0" max="10" step="0.01"
             value="{{ student.cgpa }}" required><br>
      <label>Backlogs</label><br>
      <input type="number" name="backlogs" min="0"
             value="{{ student.backlogs }}" required><br>
      <button>Save Changes</button>
      <a href="{{ url_for('students_page') }}">Cancel</a>
    </form>
    """
    return page(
        "Edit Student", content, student=student,
        departments=Department.query.order_by(Department.name).all()
    )


# =========================================================
# 11. NEW: STUDENT PROFILE AND NETWORKING
# =========================================================

@app.route("/students/profile/<int:student_id>")
@login_required
def student_profile(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return "Student not found.", 404

    content = """
    <div class="profile-header">
      <h1>{{ student.full_name }}</h1>
      <p>{{ student.department.name }} · {{ student.program }}</p>
      <p>Year {{ student.year }} · Section {{ student.section }}</p>
    </div>

    <h3>Academic Information</h3>
    <p><strong>Roll number:</strong> {{ student.roll_number }}</p>
    <p><strong>Department:</strong> {{ student.department.name }}</p>
    <p><strong>CGPA:</strong> {{ student.cgpa }}</p>
    <p><strong>Backlogs:</strong> {{ student.backlogs }}</p>

    <h3>About Me</h3>
    <p>{{ student.bio or 'This student has not added a bio yet.' }}</p>

    <h3>Skills</h3>
    <p>{{ student.skills or 'No skills added yet.' }}</p>

    <h3>Professional Links</h3>
    <div class="profile-links">
      {% if student.linkedin_url %}
      <a class="button" href="{{ student.linkedin_url }}"
         target="_blank" rel="noopener noreferrer">LinkedIn Profile</a>
      {% endif %}
      {% if student.github_url %}
      <a class="button" href="{{ student.github_url }}"
         target="_blank" rel="noopener noreferrer">GitHub Profile</a>
      {% endif %}
      {% if student.portfolio_url %}
      <a class="button" href="{{ student.portfolio_url }}"
         target="_blank" rel="noopener noreferrer">Portfolio Website</a>
      {% endif %}
    </div>
    {% if not student.linkedin_url and not student.github_url
          and not student.portfolio_url %}
      <p>No professional links added yet.</p>
    {% endif %}

    {% if current_user.role == 'admin'
          or current_user.student_id == student.id %}
      <p><a class="button" href="{{ url_for('edit_my_profile',
          student_id=student.id) }}">Edit Profile</a></p>
    {% endif %}
    <p><a href="{{ url_for('students_page') if current_user.role == 'admin'
        else url_for('student_dashboard') }}">Back</a></p>
    """
    return page("Student Profile", content, student=student)


@app.route("/students/profile/<int:student_id>/edit",
           methods=["GET", "POST"])
@login_required
def edit_my_profile(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return "Student not found.", 404

    if current_user.role != "admin":
        if (current_user.role != "student"
                or current_user.student_id != student.id):
            return "Access denied.", 403

    if request.method == "POST":
        bio = request.form.get("bio", "").strip()
        skills = request.form.get("skills", "").strip()
        linkedin = request.form.get("linkedin_url", "").strip()
        github = request.form.get("github_url", "").strip()
        portfolio = request.form.get("portfolio_url", "").strip()

        if len(bio) > 500 or len(skills) > 500:
            flash("Bio and skills must be 500 characters or fewer.")
            return redirect(url_for(
                "edit_my_profile", student_id=student.id
            ))

        links = {
            "LinkedIn": linkedin,
            "GitHub": github,
            "Portfolio": portfolio
        }
        approved_hosts = {
            "LinkedIn": {"linkedin.com", "www.linkedin.com"},
            "GitHub": {"github.com", "www.github.com"}
        }

        for label, link in links.items():
            if not link:
                continue
            parsed = urlparse(link)

            if parsed.scheme != "https" or not parsed.hostname:
                flash(f"{label} link must start with https://")
                return redirect(url_for(
                    "edit_my_profile", student_id=student.id
                ))

            if parsed.username or parsed.password:
                flash(f"Invalid {label} URL.")
                return redirect(url_for(
                    "edit_my_profile", student_id=student.id
                ))

            if label in approved_hosts and (
                parsed.hostname.lower() not in approved_hosts[label]
            ):
                flash(f"Enter a valid {label} website link.")
                return redirect(url_for(
                    "edit_my_profile", student_id=student.id
                ))

        student.bio = bio
        student.skills = skills
        student.linkedin_url = linkedin
        student.github_url = github
        student.portfolio_url = portfolio
        db.session.commit()
        flash("Profile updated successfully.")
        return redirect(url_for(
            "student_profile", student_id=student.id
        ))

    content = """
    <h1>Edit Profile: {{ student.full_name }}</h1>
    <form method="POST">
      <label>About Me</label><br>
      <textarea name="bio" maxlength="500"
          placeholder="Introduce yourself">{{ student.bio or '' }}</textarea><br>

      <label>Skills (comma-separated)</label><br>
      <textarea name="skills" maxlength="500"
          placeholder="Python, Flask, SQL">{{ student.skills or '' }}</textarea><br>

      <label>LinkedIn URL</label><br>
      <input type="url" name="linkedin_url"
          value="{{ student.linkedin_url or '' }}"
          placeholder="https://www.linkedin.com/in/your-profile"><br>

      <label>GitHub URL</label><br>
      <input type="url" name="github_url"
          value="{{ student.github_url or '' }}"
          placeholder="https://github.com/your-username"><br>

      <label>Portfolio URL</label><br>
      <input type="url" name="portfolio_url"
          value="{{ student.portfolio_url or '' }}"
          placeholder="https://your-portfolio.example"><br>

      <button type="submit">Save Profile</button>
      <a href="{{ url_for('student_profile',
          student_id=student.id) }}">Cancel</a>
    </form>
    """
    return page("Edit Profile", content, student=student)


# =========================================================
# 12. COMPANIES
# =========================================================

@app.route("/companies", methods=["GET", "POST"])
@admin_required
def companies_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        website = request.form.get("website", "").strip()
        if not name:
            flash("Company name is required.")
        elif Company.query.filter_by(name=name).first():
            flash("That company already exists.")
        else:
            db.session.add(Company(name=name, website=website))
            db.session.commit()
            flash("Company added successfully.")
            return redirect(url_for("companies_page"))

    content = """
    <h1>Company Management</h1>
    <form method="POST">
      <input name="name" placeholder="Company name" required>
      <input name="website" placeholder="Website URL">
      <button>Add Company</button>
    </form>
    <table><tr><th>ID</th><th>Company</th><th>Website</th></tr>
    {% for company in companies %}
      <tr><td>{{ company.id }}</td><td>{{ company.name }}</td>
          <td>{{ company.website or '-' }}</td></tr>
    {% else %}<tr><td colspan="3">No companies available.</td></tr>{% endfor %}
    </table>
    """
    return page(
        "Companies", content,
        companies=Company.query.order_by(Company.name).all()
    )


# =========================================================
# 13. PLACEMENT DRIVES
# =========================================================

@app.route("/drives", methods=["GET", "POST"])
@admin_required
def drives_page():
    if request.method == "POST":
        try:
            company_id = int(request.form.get("company_id", "0"))
            role = request.form.get("role", "").strip()
            package_lpa = float(request.form.get("package_lpa", "0"))
            min_cgpa = float(request.form.get("min_cgpa", "0"))
            max_backlogs = int(request.form.get("max_backlogs", "0"))
            location = request.form.get("location", "").strip()
            deadline_text = request.form.get("deadline", "").strip()

            company = db.session.get(Company, company_id)
            if not company:
                raise ValueError("Select a valid company.")
            if not role:
                raise ValueError("Job role is required.")
            if package_lpa < 0 or not 0 <= min_cgpa <= 10 or max_backlogs < 0:
                raise ValueError("Enter valid package, CGPA and backlog values.")

            deadline = date.fromisoformat(deadline_text) if deadline_text else None
            departments = []
            for value in request.form.getlist("department_ids"):
                department = db.session.get(Department, int(value))
                if department:
                    departments.append(department)
            if not departments:
                raise ValueError("Select at least one eligible department.")

            drive = Drive(
                company_id=company_id, role=role, package_lpa=package_lpa,
                min_cgpa=min_cgpa, max_backlogs=max_backlogs,
                location=location, deadline=deadline, status="Open"
            )
            drive.eligible_departments = departments
            db.session.add(drive)
            db.session.commit()
            flash("Placement drive created.")
            return redirect(url_for("drives_page"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error))

    content = """
    <h1>Placement Drives</h1>
    <h3>Create a Drive</h3>
    <form method="POST">
      <label>Company</label><br>
      <select name="company_id" required>
        <option value="">Select company</option>
        {% for company in companies %}
        <option value="{{ company.id }}">{{ company.name }}</option>
        {% endfor %}
      </select><br>
      <input name="role" placeholder="Job role" required><br>
      <input type="number" name="package_lpa" min="0" step="0.1"
             placeholder="Package in LPA" required><br>
      <input name="location" placeholder="Location"><br>
      <label>Minimum CGPA</label><br>
      <input type="number" name="min_cgpa" min="0" max="10"
             step="0.01" value="6" required><br>
      <label>Maximum backlogs</label><br>
      <input type="number" name="max_backlogs" min="0" value="0" required><br>
      <label>Deadline</label><br><input type="date" name="deadline"><br>
      <label>Eligible departments</label><br>
      {% for department in departments %}
        <label><input type="checkbox" name="department_ids"
            value="{{ department.id }}"> {{ department.name }}</label><br>
      {% endfor %}
      <button>Create Drive</button>
    </form>
    <h3>Existing Drives</h3>
    <table><tr><th>Company</th><th>Role</th><th>Package</th>
    <th>Minimum CGPA</th><th>Max Backlogs</th><th>Deadline</th><th>Status</th></tr>
    {% for drive in drives %}
    <tr><td>{{ drive.company.name }}</td><td>{{ drive.role }}</td>
        <td>{{ drive.package_lpa }}</td><td>{{ drive.min_cgpa }}</td>
        <td>{{ drive.max_backlogs }}</td><td>{{ drive.deadline or '-' }}</td>
        <td>{{ drive.status }}</td></tr>
    {% else %}<tr><td colspan="7">No drives available.</td></tr>{% endfor %}
    </table>
    """
    return page(
        "Placement Drives", content,
        companies=Company.query.order_by(Company.name).all(),
        departments=Department.query.order_by(Department.name).all(),
        drives=Drive.query.order_by(Drive.id.desc()).all()
    )


# =========================================================
# 14. APPLICATIONS
# =========================================================

@app.route("/apply/<int:drive_id>", methods=["POST"])
@student_required
def apply_drive(drive_id):
    student = db.session.get(Student, current_user.student_id)
    drive = db.session.get(Drive, drive_id)

    if not student or not drive:
        flash("Student or placement drive not found.")
        return redirect(url_for("student_dashboard"))
    if not is_student_eligible(student, drive):
        flash("You are not eligible for this placement drive.")
        return redirect(url_for("student_dashboard"))
    if Application.query.filter_by(
        student_id=student.id, drive_id=drive.id
    ).first():
        flash("You have already applied for this drive.")
    else:
        db.session.add(Application(
            student_id=student.id, drive_id=drive.id, stage="Applied"
        ))
        db.session.commit()
        flash("Application submitted successfully.")
    return redirect(url_for("student_dashboard"))


@app.route("/applications", methods=["GET", "POST"])
@admin_required
def applications_page():
    stages = ["Applied", "Shortlisted", "Online Test",
              "Interview", "Selected", "Rejected"]

    if request.method == "POST":
        try:
            application = db.session.get(
                Application, int(request.form.get("application_id", "0"))
            )
            stage = request.form.get("stage", "")
            if not application:
                raise ValueError("Application not found.")
            if stage not in stages:
                raise ValueError("Select a valid stage.")
            application.stage = stage
            db.session.commit()
            flash("Application stage updated.")
            return redirect(url_for("applications_page"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error))

    content = """
    <h1>Placement Applications</h1>
    <table><tr><th>Student</th><th>Roll Number</th><th>Company</th>
    <th>Role</th><th>Stage</th><th>Update Stage</th></tr>
    {% for application in applications %}
    <tr>
      <td><a href="{{ url_for('student_profile',
          student_id=application.student.id) }}">
          {{ application.student.full_name }}</a></td>
      <td>{{ application.student.roll_number }}</td>
      <td>{{ application.drive.company.name }}</td><td>{{ application.drive.role }}</td>
      <td>{{ application.stage }}</td>
      <td><form method="POST">
        <input type="hidden" name="application_id" value="{{ application.id }}">
        <select name="stage">{% for stage in stages %}
          <option value="{{ stage }}" {% if stage == application.stage %}selected{% endif %}>
            {{ stage }}</option>{% endfor %}</select>
        <button>Update</button></form></td>
    </tr>
    {% else %}<tr><td colspan="6">No applications available.</td></tr>{% endfor %}
    </table>
    """
    return page(
        "Applications", content,
        applications=Application.query.order_by(Application.applied_at.desc()).all(),
        stages=stages
    )


# =========================================================
# 15. NO-DUES
# =========================================================

@app.route("/clearances", methods=["GET", "POST"])
@admin_required
def clearances_page():
    statuses = ["Pending", "Cleared", "Rejected"]

    if request.method == "POST":
        try:
            clearance = db.session.get(
                StudentClearance, int(request.form.get("clearance_id", "0"))
            )
            status = request.form.get("status", "")
            if not clearance:
                raise ValueError("Clearance record not found.")
            if status not in statuses:
                raise ValueError("Select a valid clearance status.")
            clearance.status = status
            clearance.remarks = request.form.get("remarks", "").strip()
            db.session.commit()
            flash("Clearance status updated.")
            return redirect(url_for("clearances_page"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error))

    content = """
    <h1>Department No-Dues Management</h1>
    <table><tr><th>Roll Number</th><th>Student</th><th>Category</th>
    <th>Status</th><th>Remarks</th><th>Update</th></tr>
    {% for clearance in clearances %}
    <tr><td>{{ clearance.student.roll_number }}</td>
        <td><a href="{{ url_for('student_profile',
            student_id=clearance.student.id) }}">{{ clearance.student.full_name }}</a></td>
        <td>{{ clearance.category.name }}</td><td>{{ clearance.status }}</td>
        <td>{{ clearance.remarks or '-' }}</td>
        <td><form method="POST">
          <input type="hidden" name="clearance_id" value="{{ clearance.id }}">
          <select name="status">{% for status in statuses %}
            <option value="{{ status }}" {% if status == clearance.status %}selected{% endif %}>
            {{ status }}</option>{% endfor %}</select><br>
          <input name="remarks" value="{{ clearance.remarks or '' }}" placeholder="Remarks">
          <button>Save</button>
        </form></td></tr>
    {% else %}<tr><td colspan="6">No clearance records available.</td></tr>{% endfor %}
    </table>
    """
    return page(
        "No-Dues", content,
        clearances=StudentClearance.query.join(Student).order_by(
            Student.roll_number
        ).all(),
        statuses=statuses
    )


# =========================================================
# 16. CSV EXPORT AND DATABASE CHECK
# =========================================================

@app.route("/export/students.csv")
@admin_required
def export_students():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Roll Number", "Full Name", "Email", "Department", "Program",
        "Year", "Section", "Batch", "CGPA", "Backlogs",
        "Registration Status"
    ])
    for student in Student.query.order_by(Student.roll_number).all():
        writer.writerow([
            student.roll_number, student.full_name, student.email,
            student.department.name, student.program, student.year,
            student.section, student.batch, student.cgpa,
            student.backlogs, student.registration_status
        ])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        "attachment; filename=students.csv"
    )
    return response


@app.route("/db-check")
@admin_required
def db_check():
    content = """
    <h1>Database Check</h1><ul>
      <li>Departments: {{ departments }}</li><li>Students: {{ students }}</li>
      <li>Users: {{ users }}</li><li>Companies: {{ companies }}</li>
      <li>Drives: {{ drives }}</li><li>Applications: {{ applications }}</li>
      <li>Clearance Categories: {{ categories }}</li>
      <li>Student Clearances: {{ clearances }}</li>
    </ul>
    """
    return page(
        "Database Check", content,
        departments=Department.query.count(), students=Student.query.count(),
        users=User.query.count(), companies=Company.query.count(),
        drives=Drive.query.count(), applications=Application.query.count(),
        categories=ClearanceCategory.query.count(),
        clearances=StudentClearance.query.count()
    )


# =========================================================
# 17. CGPA-BASED STUDENT SELECTION
# =========================================================

@app.route("/admin/cgpa-selection", methods=["GET", "POST"])
@admin_required
def admin_cgpa_selection():
    error = None
    selected_students = []
    try:
        threshold = float(request.values.get("threshold", "8.0"))
        if not 0 <= threshold <= 10:
            raise ValueError
    except (ValueError, TypeError):
        threshold = 8.0
        error = "CGPA must be between 0 and 10."

    eligible_students = Student.query.filter(
        Student.cgpa > threshold
    ).order_by(Student.cgpa.desc()).all()

    if request.method == "POST":
        selected_ids = set(request.form.getlist("student_ids"))
        selected_students = [
            student for student in eligible_students
            if str(student.id) in selected_ids
        ]

    # Keep using your existing cgpa_selection.html template.
    return render_template(
        "cgpa_selection.html",
        threshold=threshold,
        eligible_students=eligible_students,
        selected_students=selected_students,
        error=error
    )


# =========================================================
# 18. START APPLICATION
# =========================================================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        migrate_student_profile_fields()
        seed_demo_data()
        seed_login_accounts()

    app.run(debug=True)