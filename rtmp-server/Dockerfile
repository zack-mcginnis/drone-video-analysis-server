FROM tiangolo/nginx-rtmp

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY start.sh /start.sh

RUN chmod +x /start.sh

EXPOSE 1935
EXPOSE 80
EXPOSE 8080

CMD ["/start.sh"] 