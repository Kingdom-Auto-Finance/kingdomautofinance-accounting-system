# Use an official lightweight Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Tell Streamlit to run on port 8080, headless
ENV PORT 8080
ENV STREAMLIT_SERVER_HEADLESS true
ENV STREAMLIT_SERVER_PORT 8080

# Expose port 8080 to the outside world
EXPOSE 8080

# Finally, run your Streamlit UI
CMD ["streamlit", "run", "ui.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
