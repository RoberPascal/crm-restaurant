docker build -t public-bot:latest -f Dockerfile .
docker tag public-bot:latest registry.pticasinicafamily.ru/public-bot:latest
docker push registry.pticasinicafamily.ru/public-bot:latest 