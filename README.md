# Patrol Build Tracker V3

Flask web app for tracking a Nissan Patrol build.

## Features

- Login protection
- Dashboard with progress and cost charts
- Section progress
- Tasks with filters, search, edit/delete, progress bars, and photos
- Parts with filters, edit/delete, and photos
- Costs with filters and edit/delete
- Updates/build diary with photos
- Mobile friendly layout
- SQLite database
- Render-ready persistent database and upload folder support

## Local run

```bash
python -m pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

Default login:

```text
Username: admin
Password: patrol123
```

## Render settings

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app
```

Recommended environment variables in Render:

```text
APP_USERNAME=yourusername
APP_PASSWORD=yourpassword
SECRET_KEY=make-a-long-random-secret
```

Recommended disk:

```text
Mount path: /var/data
```

The app automatically uses `/var/data/patrol_build.db` and `/var/data/uploads` when available.


## Notes

- Render/Gunicorn database init fix included.
- The app creates missing tables automatically on startup.
