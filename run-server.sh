#!/bin/bash
# Unix/Linux startup script for Route Fuel Planner API

echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "Running Django checks..."
python manage.py check

echo ""
echo "Running tests..."
python manage.py test

echo ""
echo "Starting development server..."
echo "API will be available at: http://localhost:8000/api/route-plan/"
echo ""
python manage.py runserver
