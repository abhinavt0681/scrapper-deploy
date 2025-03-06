import os
import time
import csv
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import boto3

# --- Configuration ---
USERNAME = "cn255243"          # your agent ID
PASSWORD = "King314159!!!"      # your password

BASE_URL    = "https://h3c.mlspin.com"
LOGIN_URL   = BASE_URL + "/signin.asp#ath"
SEARCH_URL  = BASE_URL + "/tools/mshare/search.asp"
RESULTS_URL = BASE_URL + "/tools/mshare/results.asp"

# Define the S3 bucket name where results will be stored
S3_BUCKET = "gh-scrapping"

# Set the year range (will loop 1995 to 2024)
start_year = 1995
end_year   = 2025  

# --- Utility: Load options CSV ---
def load_options(csv_filename):
    """
    Loads options from a CSV file and returns a list of dictionaries.
    Each dictionary has keys: 'option_value' and 'option_text'.
    """
    options = []
    with open(csv_filename, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            options.append(row)
    return options

# --- Step 1. Use Selenium to log in and get session cookies ---
def selenium_login():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # If necessary, specify the location of your Chrome binary:
    # chrome_options.binary_location = '/usr/bin/google-chrome'
    
    service = Service(executable_path="./chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    wait = WebDriverWait(driver, 10)
    
    driver.get(LOGIN_URL)
    # Wait for login form fields to be clickable
    user_input = wait.until(EC.element_to_be_clickable((By.NAME, "user_name")))
    pass_input = wait.until(EC.element_to_be_clickable((By.NAME, "pass")))
    
    # (Optionally, dismiss any overlay)
    time.sleep(2)
    try:
        ok_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='OK']")))
        ok_button.click()
        print("Overlay OK button clicked.")
        time.sleep(1)
    except Exception:
        print("No overlay OK button found or already dismissed.")
    
    # Enter credentials and submit the form
    user_input.clear()
    user_input.send_keys(USERNAME)
    pass_input.clear()
    pass_input.send_keys(PASSWORD)
    driver.find_element(By.ID, "loginForm").submit()
    
    # Wait until we are on the search page (or force navigation)
    try:
        wait.until(EC.url_contains("tools/mshare/search.asp"))
    except Exception:
        driver.get(SEARCH_URL)
    print("Logged in successfully (or forced navigation to search page).")
    return driver

# --- Step 2. Extract cookies from Selenium and set them in a requests Session ---
def create_requests_session(driver):
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"])
    # It can help to mimic a real browser
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
                      "AppleWebKit/537.36 (KHTML, like Gecko) " +
                      "Chrome/105.0.0.0 Safari/537.36",
        "Referer": SEARCH_URL,
    })
    return session

# --- Step 3. Prepare the POST payload based on the search form ---
def build_payload(neighborhood_value, year):
    payload = {
        "DeleteScrollCookies": "Y",
        "ReportType": "5",  # Total Sold Market Statistics
        "TimeFrame": "",
        "StartDate": f"01/01/{year}",
        "EndDate": f"01/01/{year+1}",
        "tareaslisting": neighborhood_value,
        "proptype": "mf",  # For multifamily
        "Changes": "yes",
        "NumResults": "100",
    }
    return payload

# --- Step 4. Perform a search request and save results to S3 ---
def perform_search(session, neighborhood_value, year, save_dir):
    payload = build_payload(neighborhood_value, year)
    print(f"Performing search for year {year} with payload: {payload}")
    response = session.post(RESULTS_URL, data=payload)
    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code} for year {year}")
    else:
        if "Enter Your Agent ID" in response.text:
            print("Warning: Received login page instead of search results.")
        # Upload the results to S3
        s3 = boto3.client('s3')
        s3_key = f"{save_dir}/results_{year}.html"
        s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=response.text, ContentType='text/html')
        print(f"Saved results for {year} to S3 bucket '{S3_BUCKET}' with key '{s3_key}'.")

# --- Utility: Parse option text to extract town and area ---
def parse_option_text(option_text):
    """
    Given an option text like "Worthington, MA-Worthington Center", 
    extract the town and the area (if available). Returns (town, area).
    If no area is provided, area will be None.
    """
    option_text = option_text.strip()
    parts = option_text.split(",")
    town = parts[0].strip()
    area = None
    if len(parts) > 1:
        dash_parts = parts[1].split("-")
        if len(dash_parts) > 1:
            area = dash_parts[1].strip()
    return town, area

# --- Main Script ---
def main():
    # Load options from CSV (e.g., options.csv)
    options = load_options("options.csv")
    
    # Step 1: Log in with Selenium (headless)
    driver = selenium_login()
    
    # Step 2: Create a requests session with cookies from Selenium
    session = create_requests_session(driver)
    
    # Optionally navigate to the search page in Selenium to confirm session is active
    driver.get(SEARCH_URL)
    time.sleep(2)
    
    # Loop over each option from the CSV
    for opt in options:
        option_value = opt["option_value"]  # e.g., "ACTN"
        option_text = opt["option_text"]      # e.g., "Acton, MA"
        town, area = parse_option_text(option_text)
        
        # For multifamily, we now use the option_value directly (do not append _mf)
        effective_value = option_value
        
        # Determine the save directory.
        # Group by town; if area is available, further create an "areas" subfolder.
        if area:
            save_dir = f"mf/{town}/{area}"
        else:
            save_dir = f"mf/{town}"
        
        print(f"\nProcessing option: {option_text} -> effective value: {effective_value}, save_dir: {save_dir}")
        
        # Loop over each year in the defined range.
        for year in range(start_year, end_year):
            perform_search(session, effective_value, year, save_dir)
            time.sleep(0.5)  # small delay between requests
    
    driver.quit()

if __name__ == "__main__":
    main()
