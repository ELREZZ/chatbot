from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

BASE = "https://petshoplesorangers.tn"

CATEGORY_URLS = [
    "https://petshoplesorangers.tn/category/alimentation-ye8bb",
    "https://petshoplesorangers.tn/category/litire--propriet-s2xt8",
    "https://petshoplesorangers.tn/category/alimentation-dh5we"
]

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
wait = WebDriverWait(driver, 10)

all_products = []

for category in CATEGORY_URLS:
    print(f"\n📂 Category: {category}")
    driver.get(category)

    page_num = 1

    while True:
        print(f"➡️ Page {page_num}")

        # Wait for products
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/product/']")))

        cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        print(f"Found {len(cards)} products")

        for c in cards:
            try:
                link = c.get_attribute("href")
                name = c.text.strip()

                if not link or not name:
                    continue

                all_products.append({
                    "name": name,
                    "link": link
                })
            except:
                pass

        # 🔽 Go to next page
        page_num += 1

        try:
            next_btn = driver.find_element(By.XPATH, f"//a[normalize-space()='{page_num}']")
        except:
            print("⛔ No more pages")
            break

        # Save current first product to detect page change
        first_product = cards[0].get_attribute("href")

        try:
            # ✅ Scroll to button
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(1)

            # ✅ JS click (fixes your error)
            driver.execute_script("arguments[0].click();", next_btn)

        except Exception as e:
            print(f"⚠️ Click failed: {e}")
            break

        # ✅ Wait until new content loads (IMPORTANT)
        try:
            wait.until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")[0].get_attribute("href") != first_product
            )
        except:
            print("⚠️ Page did not change, stopping")
            break

        time.sleep(1)

driver.quit()

# 🔥 Remove duplicates
unique = {p["link"]: p for p in all_products}.values()

print(f"\n✅ TOTAL UNIQUE PRODUCTS: {len(unique)}")

# 📝 Save results
with open("products.txt", "w", encoding="utf-8") as f:
    for p in unique:
        f.write(f"{p['name']} | {p['link']}\n")

print("📄 Saved to products.txt")