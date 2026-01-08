# kingdomautofinance-accounting-system
Kingdom Auto Finance Accounting System - Structure:

payment_fetcher.py   – moves new payments into the log
payment_processor.py – applies payments to each loan’s schedule
reporting.py         – creates summary reports
daily_summary_reporter.py – creates the daily report
gutils.py            – handles Google login and sheet access
main.py              – runs all steps on command
ui.py                – shows buttons in the web dashboard
config.py            – holds your sheet and folder IDs

-------------------------

### Commands:

### Import of spreadsheets amortization from google drive into supabase
python src/bootstrap.py

### Reads the payment log from Kingdom and transfer the payments with loanid into supabase.
python src/main.py fetch_payments

### Fetch payments for all time (check duplicates)
python src/main.py fetch_payments --all

### Fetch payments for last 7 days (Default)
python src/main.py fetch_payments --recent 7

### Process the payments and insert them into each amortization schedule
python src/main.py process

### Runs the report summary
python src/main.py report --all

### Runs the report summary within a date range
python src/main.py report 2025-05-01 2025-05-14

### Runs the report with totals grouped by payment date within a date range (or --all):
python src/main.py report day-breakdown 2025-05-01 2025-05-14

### Runs the report with totals grouped by loanid within a date range (or --all)
python src/main.py report --all loan-breakdown

### Runs the report with totals grouped by loanid and then by date within a date range (or --all)
python src/main.py report --all full-breakdown

-------------------------

### Google Cloud Instance Details 

### Set the kaf accounting system project on google cloud
gcloud config set project kingdomaccountingsystem

### Log in and authenticate Google user
gcloud auth application-default login

### Build and submit a new version
gcloud builds submit \
  --tag gcr.io/kingdomaccountingsystem/kingdom-autofinance:latest

### Deploy the new version
gcloud run deploy kingdom-autofinance \
  --image gcr.io/kingdomaccountingsystem/kingdom-autofinance:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated

-------------------------

##### Instance Details #####

### Deactivate current virtual environment
deactivate

### Create a virtual environment
python3 -m venv ~/global-venv

### Activate the virtual environment
source ~/global-venv/bin/activate

### Install all the requirements
pip install -r requirements.txt

### List all google cloud projects id
gcloud projects list

### Show all files and folders size
du -sh * .[^.]* | sort -h

### Clean cache directories
rm -rf ~/.cache ~/.config ~/.streamlit __pycache__

### Delete venv/ and global-venv/ directories
rm -rf ~/venv/ ~/global-venv/

### Clean log files
rm -rf ~/logs/* - clear logs

-------------------------

### Entire redeployment run
rm -rf ~/venv/ ~/global-venv/
rm -rf ~/.cache ~/.config ~/.streamlit __pycache__

gcloud builds submit \
  --tag gcr.io/kingdomaccountingsystem/kingdom-autofinance:latest

gcloud run deploy kingdom-autofinance \
  --image gcr.io/kingdomaccountingsystem/kingdom-autofinance:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated

  deactivate
  python3 -m venv ~/global-venv
  source ~/global-venv/bin/activate
  pip install -r requirements.txt