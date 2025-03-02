# Hydrolink integration for Home Assistant

Hydrolink is a remote water meter reading service provided by Koka Oy. This integration reads the meter readings from the Hydrolink API.

## Configuration

```yaml
sensor:
  - platform: hydrolink
    username: "<username>"
    password: "<password>"
```
