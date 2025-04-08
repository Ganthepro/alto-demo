import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from pyvirtualdisplay import Display
display = Display(visible=0, size=(800, 600))
display.start()

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--start-maximized')

driver = webdriver.Chrome(options=chrome_options)
driver.get('http://192.168.1.116')
# html = driver.page_source
# print(html[:100])
# driver.save_screenshot("headless_screenshot.png")
ele = driver.find_element_by_id("but3")
ele.submit()
time.sleep(2.0)
# driver.save_screenshot("headless_screenshot.png")
form = driver.find_element_by_xpath("//form[@action='mq']")
form.submit()
time.sleep(2.0)
# driver.save_screenshot("headless_screenshot.png")
ele = driver.find_element_by_id("mh")
ele.clear()
ele.send_keys("192.168.1.105")
ele = driver.find_element_by_id("ml")
ele.clear()
ele.send_keys("1883")
ele = driver.find_element_by_id("mu")
ele.clear()
ele.send_keys("alto")
ele = driver.find_element_by_id("mp")
ele.clear()
ele.send_keys("altotech")
ele = driver.find_element_by_name("save")
ele.click()
is_not_save = True
count = 0
while is_not_save:
    try:
        ele = driver.find_element_by_xpath("//*[text()='Configuration saved']")
        is_not_save = False
        print(ele.tag_name)
        print(ele.get_attribute('innerHTML'))
    except Exception as e:
        print(e)
    time.sleep(0.2)
    count += 1
driver.save_screenshot("headless_screenshot.png")
driver.quit()
print(count)
