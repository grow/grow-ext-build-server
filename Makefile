project := grow-ext-build-server
version := dev

app_identity_email ?= $(project)@appspot.gserviceaccount.com
app_identity_key_path ?= key.pem

run:
	dev_appserver.py \
		--appidentity_email_address $(app_identity_email) \
    --appidentity_private_key_path $(app_identity_key_path) \
		example/app.yaml
