# import pickle
# from google.oauth2.credentials import Credentials

# # Path to your token file
# with open("token_gmail.pkl", "rb") as f:
#     creds = pickle.load(f)

# # creds should be a google.oauth2.credentials.Credentials object
# print("Refresh Token:", creds.refresh_token)

from Outlook.outlook_auth import OutlookAuth

auth = OutlookAuth()
token = auth.get_access_token()  # Opens browser
print(token)  # Optional: inspect the token
