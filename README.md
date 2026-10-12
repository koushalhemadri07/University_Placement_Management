# University Placement Portal

A Flask demo portal for managing student placements, company drives,
applications, and departmental no-dues clearances.

## Demo accounts

The demo data includes these accounts:

- Admin: `admin@university.local`
- Student: `demo001@example.com`

Set the passwords yourself with the `ADMIN_PASSWORD` and `STUDENT_PASSWORD`
environment variables. Do not use real account passwords.

## Run locally

In PowerShell, open this project folder and set demo passwords for the current
terminal session:

```powershell
$env:ADMIN_PASSWORD = "choose-a-demo-admin-password"
$env:STUDENT_PASSWORD = "choose-a-demo-student-password"
python app.py
```

Open <http://127.0.0.1:5000>.

## Deploy on Render

1. In Render, choose **New +** → **Web Service**, then connect the public
   `koushalhemadri07/University_Placement2` GitHub repository.
2. Select the `main` branch and choose the **Python** runtime.
3. Set the build command to `pip install -r requirements.txt`.
4. Set the start command to `gunicorn app:app`.
5. Add these environment variables in the Render service settings:
   - `SECRET_KEY`: a long, randomly generated value.
   - `ADMIN_PASSWORD`: a strong demo admin password.
   - `STUDENT_PASSWORD`: a strong demo student password.
6. Create the service and wait for its deploy to finish. Open the public URL
   Render provides.

The app creates and seeds its SQLite database when it starts. SQLite data on a
host without persistent storage can be reset by a restart or redeploy, so use
this setup only for fake demo data. Do not put real student information in this
public demo.
