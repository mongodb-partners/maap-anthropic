#!/usr/bin/env bash

cd main
docker build --tag 'main' .

cd ../ui 
docker build --tag 'ui' .

cd ../loader 
docker build --tag 'loader' .

cd ../logger 
docker build --tag 'logger' .

cd ../nginx 
docker build --tag 'nginx' .