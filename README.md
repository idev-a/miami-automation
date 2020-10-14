# miami-scripts

## create virtual env
python -m venv venv

source venv/bin/activate

## install packages
pip install -r requirements.txt

##create dir
mkdir /home/ubuntu/.config/
mkdir /home/ubuntu/.config/gspread_pandas/

## copy google credential
cp creds/google_secret.json /home/ubuntu/.config/gspread_pandas/

## run as background
nohup /home/ubuntu/miami-scripts/venv/bin/python /home/ubuntu/miami-scripts/mas.py &