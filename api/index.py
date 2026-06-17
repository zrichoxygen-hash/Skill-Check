import sys
sys.path.append("../../backend")
from app import app as vercel_app

# Vercel expects a variable named 'app' or 'vercel_app' for Python deployments
app = vercel_app
