docker swarm init

docker volume create pgdata
docker volume create static_volume
docker volume create letsencrypt
docker volume create logs
docker volume create error
docker volume create nginx.conf
docker volume create fail2ban_config
docker volume create recordings
docker volume create postgres-data

  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create SECRET_KEY -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create AWS_REGION -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create AMI_ID - 
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create GUAC_DB_HOST -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create INSTANCE_TYPE -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create windows_key -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create KEY_NAME -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create SECURITY_GROUP -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create AMI_WIN_PASS - 
  echo "guacamole" | docker secret create  GUACAMOLE_SERVER -
  echo "timDBA" | docker secret create DB_USER -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create DB_PASSWORD -
  echo "Gu" | docker secret create DB_NAME -
  #GUACAMOLE_USERNAME -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create GUACAMOLE_PASSWORD -
  #AWS_SECRET_ACCESS_KEY
  #AWS_ACCESS_KEY_ID
  #SECURITY_GROUP -
  #AMI_WIN_PASS -
  #GUACAMOLE_SERVER -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create DATABASE_NAME -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create DATABASE_USER -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create DATABASE_PASSWORD -
  #RDP_ENCRYPTION_KEY -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create postgres_password -
  cat /dev/urandom | tr -dc 'a-zA-Z0-9$%&%' | fold -w 12 | head -n 1 | docker secret create web_postgres_password -

read -p "Please enter your AWS key: " key
echo $key | docker secret create AWS_SECRET_ACCESS_KEY -

read -p "Please enter your AWS key: " key
echo $key | docker secret create AWS_ACCESS_KEY_ID -
