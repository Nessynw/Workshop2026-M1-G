FROM eclipse-mosquitto:2

COPY passwd /mosquitto/config/passwd
COPY config/acl /mosquitto/config/acl

RUN chown mosquitto:mosquitto /mosquitto/config/passwd /mosquitto/config/acl \
    && chmod 0700 /mosquitto/config/passwd /mosquitto/config/acl