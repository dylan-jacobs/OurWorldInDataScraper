from math import nan
import time
from tkinter import NO
from httpx import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
from dotenv import load_dotenv
import re
import random
import csv
import google.generativeai as genai

URLS_TEXT_FILE_NAME = 'urls.txt'
URL_INDEX_FILE_NAME = 'url_index.txt'
DATA_CSV_FILE_NAME = 'data.csv'
NUM_RANDOM_COUNTRIES_TO_PICK_DATA_FROM = 20
COUNTRIES_TO_ALWAYS_INCLUDE = ['United States', 'United Kingdom', 'China', 'Japan', 'Germany', 'Canada', 'Mexico', 'Brazil', 'South Africa', 'Saudi Arabia']
"""
load_dotenv()
GOOGLE_GEMINI_API_KEY = os.environ.get('GOOGLE_GEMINI_API_KEY')
genai.configure(api_key=GOOGLE_GEMINI_API_KEY)
gemini_model = genai.GenerativeModel(
    'gemini-1.5-flash',
    generation_config=genai.GenerationConfig(
        max_output_tokens=60,
        temperature=0.5,
    ))
"""

def launch(url, headless=False):
    service = Service()
    
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--incognito')
    if headless: chrome_options.add_argument('--headless')
    chrome_options.add_argument("--disable-gpu")  # Necessary for headless mode on Windows
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
    chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get(url)
    return driver

def get_urls():
    url_index = 0
    # get next url to read from
    if os.path.exists(URL_INDEX_FILE_NAME):
        with open(URL_INDEX_FILE_NAME, 'r') as txt:
            url_index = int(txt.readline())
    if os.path.exists(URLS_TEXT_FILE_NAME):
        with open(URLS_TEXT_FILE_NAME, 'r') as txt:
            return txt.readlines(), url_index
        
    # create urls file, reading from Explore page on OWID website
    base_url = 'https://ourworldindata.org/charts'
    driver = launch(base_url, headless=True)
    content = driver.find_element(By.XPATH, '/html/body/main/div/div/div[2]/div')
    containers = content.find_elements(By.TAG_NAME, 'section')
    for container in containers:
        data_links_container = container.find_element(By.TAG_NAME, 'ul')
        data_links = data_links_container.find_elements(By.XPATH, '*')
        print(len(data_links))
        urls = [data_link.find_element(By.TAG_NAME, 'a').get_attribute('href') for data_link in data_links]
        with open(URLS_TEXT_FILE_NAME, 'a') as txt:
            for url in urls:
                txt.write(str(url) + '\n')
    
    return urls, url_index

def select_countries(driver):
    # Adjust the timeout and condition as necessary
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, 'EntitySearchResults.VerticalScrollContainer'))
    )
    # Wait until the page is fully loaded
    try:
        countries_list = driver.find_element(By.CLASS_NAME, 'EntitySearchResults.VerticalScrollContainer')
        countries = countries_list.find_elements(By.XPATH, '*')
        num_countries = len(countries)
        indices = random.sample(range(min(5, num_countries), num_countries), min(num_countries, NUM_RANDOM_COUNTRIES_TO_PICK_DATA_FROM))
        print(num_countries)
        for i in indices:
            try:
                checkbox = countries[i].find_element(By.TAG_NAME, 'div')
                driver.execute_script("arguments[0].scrollIntoView();", checkbox)
                checkbox.click()
            except Exception as e:
                # error occured, nvm
                print("Error occured in country clicking: ", e)
    except Exception as e:
        print("An error occurred:", e)

def prepare_page(driver, limit_results=False):
    # Wait until the page is fully loaded     
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, 'CaptionedChart')))
    
    # if you want to limit table results, do this
    if limit_results:
        select_countries(driver)

    try:    
        table_btn = driver.find_element(By.CSS_SELECTOR, "button[data-track-note='chart_click_table']")
        table_btn.click()
        time.sleep(2)
    except NoSuchElementException:
        print('No Such Element Exception (Table Button Click!)')

    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'tbody'))) # wait for table to load before proceeding

    try:
        title = driver.find_element(By.XPATH, "//div[@class='HeaderHTML']/div/h1/span/span")
        title_string = title.text             
    except NoSuchElementException:
        print('No Such Element Exception (Title String!)')
        title_string = nan

    try:
        parent = driver.find_element(By.XPATH, "//div[@class='HeaderHTML']/div/p/span")
        header_string = get_header(parent)
    except NoSuchElementException:
        print('No Such Element Exception: (No Header)')
        header_string = ''
    
    # only after the data is shown in table format will this switch appear
    if limit_results:
        # Wait until the table format is loaded
        try:
            # Adjust the timeout and condition as necessary
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[data-track-note='chart_filter_table_rows']"))
            )
        except Exception as e:
            print("An error occurred:", e)
        try:
            show_selected_countries_only_btn = driver.find_element(By.CSS_SELECTOR, "input[data-track-note='chart_filter_table_rows']")
            show_selected_countries_only_btn.click()
            time.sleep(2)
        except NoSuchElementException:
            print('No Such Element Exception (Show Selected Countries Only Button Click!)')

    if isinstance(title_string, str): 
        title_string = re.sub(r', \d{4} to \d{4}', '', str(title_string)) # remove the string ', 19xx to 2022' (hopefully)

    return title_string, header_string

def get_date_and_type_from_table(driver):
    try:
        header = driver.find_element(By.TAG_NAME, 'thead')
        date = header.find_element(By.XPATH, './/tr/th[3]/div/span[2]').text
    except NoSuchElementException:
        try:
            header = driver.find_element(By.TAG_NAME, 'thead')
            date = header.find_element(By.XPATH, './/tr/th[2]/div/div/span[2]').text
        except NoSuchElementException:
            print('No Such Element Exception: No specific date')
            date = nan
    try:
        type = header.find_element(By.XPATH, './/tr[1]/th[2]/div/span/div[1]').text
    except Exception:
        print('No Such Element Exception: No specific type')
        type = ''
    
    return date, type

def get_data_from_row(row):

    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, 'entity.sorted')))
    country = nan
    amount = nan
    try:
        country = row.find_element(By.CLASS_NAME, 'entity.sorted').text
        amount = row.find_element(By.XPATH, ".//td[@class='dimension dimension-end']/span[not(@class)]").text
    except NoSuchElementException:
        try:
            country = row.find_element(By.CLASS_NAME, 'entity.sorted').text
            amount = row.find_element(By.XPATH, ".//td[@class='dimension dimension-single']/*/span[not(@class)]").text
        except NoSuchElementException:
            print('No Such Element Exception! (Row Data!)')

    return country, amount

def write_data_to_csv(data):
    file_exists = os.path.exists(DATA_CSV_FILE_NAME)
    with open(DATA_CSV_FILE_NAME, 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['Title', 'Header', 'Type', 'Date', 'Country', 'Amount'])
        writer.writerows(data)
    file.close()

def get_header(parent_element):
    header_string = ''
    try:
        children = parent_element.find_elements(By.XPATH, './*')
        if children:
            for child in children:
                header_string += ' ' + get_header(child)
        else:
            header_string += ' ' + parent_element.text
    except NoSuchElementException:
        print('Error: (No header)')
        header_string = ''
    return header_string.strip()

def update_url_index(i):
    with open(URL_INDEX_FILE_NAME, 'w') as txt:
        txt.write(str(i))

def parse_rows(rows, rows_container):
    row_set = set()

    # always get data from these countries
    for title in COUNTRIES_TO_ALWAYS_INCLUDE:
        try:
            row_set.add(rows_container.find_element(By.XPATH, f".//tr[td[contains(text(), '{title}')]]"))
        except NoSuchElementException:
            pass

    # add some more random countries
    timeout = 0
    while (len(row_set) < (len(COUNTRIES_TO_ALWAYS_INCLUDE) + NUM_RANDOM_COUNTRIES_TO_PICK_DATA_FROM)) & (timeout < 2*NUM_RANDOM_COUNTRIES_TO_PICK_DATA_FROM):
        row_set.add(rows[random.randint(0, len(rows)-1)])
        timeout+=1
    return list(row_set)

"""
def generate_pretty_title(title, country, date):
    message = f'Generate a more readable title for this graph of title: {title}, date: {date}, country: {country} and only print out one suggestion, please'
    return gemini_model.generate_content(message).text
"""
    
urls, starting_index = get_urls()
num_urls = len(urls)

for i in range(starting_index, num_urls):
    try:
        url = urls[i]
        driver = launch(url, headless=False)
        title, header = prepare_page(driver)
        print(f'------------------- {header} --------------------')

        try:
            date, type = get_date_and_type_from_table(driver)
            print(type)
            table = driver.find_element(By.TAG_NAME, 'tbody')
            rows = table.find_elements(By.CSS_SELECTOR, "tr:not(.title)")
        except NoSuchElementException:
            print('No Such Element Exception (Table!)')

        data = []
        rows = parse_rows(rows, table)
        for row in rows:
            country, amount = get_data_from_row(row)
            if (country == nan) | (amount == nan) | (amount == '') | (amount == ' '): continue # skip NaN values
            data.append([title, header, type, date, country, amount])
            # print(generate_pretty_title(title, country, date))
            sentence = f'{title} in {date} - {country}: \n Over or Under {amount}?'
            print(sentence)
        driver.quit()

        # write data block from respective category to CSV
        write_data_to_csv(data)
        update_url_index(i+1) # start at next url
    except TimeoutException:
        print('-------------------> TIMEOUT EXCEPTION | TRYING AGAIN....')
        i -= 1



















