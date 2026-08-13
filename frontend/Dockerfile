FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY index.html /usr/share/nginx/html/index.html
COPY src /usr/share/nginx/html/src

# En Docker, nginx proxifie l'API sur la meme origine : on remplace la config
# de dev (qui pointe sur localhost:8000) par une base vide.
COPY config.docker.js /usr/share/nginx/html/src/config.js

EXPOSE 80
