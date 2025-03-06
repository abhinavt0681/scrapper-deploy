import os
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuration ---
USERNAME = "cn255243"          # your agent ID
PASSWORD = "King314159!!!"      # your password

BASE_URL    = "https://h3c.mlspin.com"
LOGIN_URL   = BASE_URL + "/signin.asp#ath"
SEARCH_URL  = BASE_URL + "/tools/mshare/search.asp"
RESULTS_URL = BASE_URL + "/tools/mshare/results.asp"

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
    "quincy_mf":"QUIN",
    "braintree_mf":"BRAI",
    "belmont_mf":"BLMT"
    # add more as needed...
}

start_year = 1995
end_year   = 2025  # will loop 1995 to 2024

# --- Step 1. Use Selenium to log in and get session cookies ---
def selenium_login():
    service = Service(executable_path="./chromedriver")
    driver = webdriver.Chrome(service=service)
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
        # The search form uses a hidden field (tareaslisting) to hold selected towns.
        # (In the browser you’d normally select a town which then populates this field.)
        # Here we assume that sending the town’s value is enough.
        "tareaslisting": neighborhood_value,
        # Also include property type if needed (e.g., for Single Family use "sf")
        "proptype": "mf",
        # Some other hidden fields might be required; you may need to inspect the actual POST request.
        "Changes": "yes",
        "NumResults": "100",
    }
    return payload

# --- Step 4. Perform a search request and save results ---
def perform_search(session, neighborhood_value, year, save_dir):
    payload = build_payload(neighborhood_value, year)
    print(f"Performing search for year {year} with payload: {payload}")
    response = session.post(RESULTS_URL, data=payload)
    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code} for year {year}")
    else:
        # Check if we got the login page again (e.g. by looking for a known login element)
        if "Enter Your Agent ID" in response.text:
            print("Warning: Received login page instead of search results.")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        file_path = os.path.join(save_dir, f"results_{year}.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"Saved results for {year} to {file_path}")

# --- Main Script ---
def main():
    # Step 1: Log in with Selenium
    driver = selenium_login()
    # Now you can (optionally) close the Selenium browser if you don't need it further,
    # but keep it open so that cookies are available.
    
    # Step 2: Create a requests session with the cookies from Selenium
    session = create_requests_session(driver)
    
    # (Optional) Navigate to the search page in Selenium so you know the session is active
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
