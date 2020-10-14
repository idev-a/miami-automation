# miami-scripts

## install python3-venv
sudo apt-get update
sudo apt-get install python3-venv

## create virtual env
python3 -m venv venv

## activate venv
source venv/bin/activate

## install packages
pip install -r requirements.txt

##create dir
mkdir /root/.config/ && mkdir /root/.config/gspread_pandas/

## copy google credential
cp creds/google_secret.json /root/.config/gspread_pandas/

## run as background
nohup /root/miami-scripts/venv/bin/python /root/miami-scripts/mas.py &