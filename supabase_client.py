from supabase import create_client, Client

# Replace with your actual values from Supabase > Settings > API
SUPABASE_URL = "https://puwcyhbjchkfvvaccacg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB1d2N5aGJqY2hrZnZ2YWNjYWNnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDcyMzE2ODMsImV4cCI6MjA2MjgwNzY4M30.e8pc5dXm-1cCJzahDzSZk51C3IZ7GuVuhJmRjZ6-c8Y"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)