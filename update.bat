@echo off
echo Atualizando SIG Server...
docker stop sig-server
docker rm sig-server
docker build -t sig-server https://github.com/87borges/sig-server.git
docker run -d -p 5002:5000 --name sig-server --restart unless-stopped sig-server
echo Pronto!
pause
