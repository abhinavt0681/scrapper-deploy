import os
import time
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

# Define the neighborhoods (adjust as needed)
neighborhoods = {
    "framingham_mf": "FRAM",
    "andover_mf": "ANDO",
    "southborough_mf": "SBRO",
    "wayland_mf": "WAYL",
    "ayer_mf": "AYER",
    "groton_mf": "GRTN",
    "leominster_mf": "LMNS",
    "hopkinton_mf": "HPKN",
    "fitchburg_mf": "FTCH",
    "quincy_mf": "QUIN",
    "braintree_mf": "BRAI",
    "belmont_mf": "BLMT"
    # add more as needed...
}

start_year = 1995
end_year   = 2025  # will loop 1995 to 2024

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
    
    # Wait until we are on the search page (or forced there)
    try:
        wait.until(EC.url_contains("tools/mshare/search.asp"))
    except Exception:
        # If we get redirected to a login error page, force navigation:
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
        "proptype": "mf",
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

# --- Main Script ---
def main():
    # Step 1: Log in with Selenium (headless)
    driver = selenium_login()
    
    # Step 2: Create a requests session with cookies from Selenium
    session = create_requests_session(driver)
    
    # Optionally navigate to the search page in Selenium to confirm session is active
    driver.get(SEARCH_URL)
    time.sleep(2)
    
    # For each neighborhood, loop through the years and perform searches
    for dir_name, neighborhood_value in neighborhoods.items():
        print(f"\nProcessing neighborhood: {dir_name}")
        for year in range(start_year, end_year):
            perform_search(session, neighborhood_value, year, dir_name)
            time.sleep(0.5)  # small delay between requests
    
    driver.quit()

if __name__ == "__main__":
    main()
