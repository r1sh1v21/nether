import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Target URL
url = "https://www.internetbumperstickers.com/attitude/"

# Folder to save images
folder = "downloaded_banners"
os.makedirs(folder, exist_ok=True)

# Get the page content
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")

# Find all image tags
images = soup.find_all("img")

# Loop through and save each image
for index, img in enumerate(images, start=1):
    img_url = urljoin(url, img.get("src"))
    extension = os.path.splitext(img_url)[1].split("?")[0]  # get .jpg, .png etc.
    filename = f"banner{index}{extension}"
    filepath = os.path.join(folder, filename)

    try:
        with requests.get(img_url, stream=True) as r:
            if r.status_code == 200:
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
                print(f"Downloaded: {filename}")
            else:
                print(f"Failed to download: {img_url}")
    except Exception as e:
        print(f"Error downloading {img_url}: {e}")

print("All images downloaded.")
