# Hydrolink integration for Home Assistant

Hydrolink is a remote water meter reading service provided by Koka Oy. This integration reads the meter readings from
the Hydrolink API.

The integration creates a sensor for each meter found from the API. The current value of the sensors is the current
meter reading. The sensor contains the following attributes:

- `warm` — Indicates whether the meter is for warm water.
- `daily_consumption` — Historical consumption for the past 7 days.

`daily_consumption` is a list containing one entry per day. It can be used to display historical water consumption using
the ApexCharts card. Each entry contains three values:

- `timestamp` — Timestamp in ms.
- `date` — The timestamp formatted as a date `YYYY-MM-DD`.
- `value` — Water consumption, i.e. difference in the meter reading to the previous day.


## Configuration

Confguration is very simple. You just need to provide your username and password to the Hydrolink API.

```yaml
sensor:
  - platform: hydrolink
    username: "<username>"
    password: "<password>"
```


## Displaying a chart

The easiest way to display a chart of historical water consumption is using the
[ApexCharts](https://github.com/RomRider/apexcharts-card) card, since its
[`data_generator`](https://github.com/RomRider/apexcharts-card?tab=readme-ov-file#data_generator-option) option allows
reading the consumption from the `daily_consumption` attribute.

```yaml
type: custom:apexcharts-card
graph_span: 7d
header:
  title: Water Consumption
  show: true
series:
  - entity: sensor.hydrolink_01234567
    type: column
    data_generator: >
      return entity.attributes.daily_consumption.map((entry, index) => {
        return [entry["timestamp"], entry["value"]];
      });
```

If you want to use another card, or you want to display the consumption for different intervals, the readings need to be
cached and the periodical consumption needs to be computed from the meter readings. For this, Home Assistant provides
the [Utility Meter](https://www.home-assistant.io/integrations/utility_meter/) integration.

```yaml
utility_meter:
  cold_water_consumption:
    source: sensor.hydrolink_01234567
    name: Cold Water Comsumption
    cycle: daily
  warm_water_consumption:
    source: sensor.hydrolink_01234568
    name: Warm Water Comsumption
    cycle: daily
```

Once Home Assistant has accumulated enough data, you can use any chart card, for example the
[Mini Graph](https://github.com/kalkih/mini-graph-card) card to display the Utility Meter values.

```yaml
type: custom:mini-graph-card
name: Water Consumption
hours_to_show: 168
group_by: date
aggregate_func: max
show:
  graph: bar
entities:
  - entity: sensor.cold_water_consumption
    name: Cold
  - entity: sensor.warm_water_consumption
    name: Warm
```
