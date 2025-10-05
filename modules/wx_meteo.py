#import openmeteo_requests # pip install openmeteo-requests
#from retry_requests import retry # pip install retry_requests

import requests
import json
from modules.log import *

def get_weather_data(api_url, params):
    response = requests.get(api_url, params=params)
    response.raise_for_status()  # Raise an error for bad status codes
    return response.json()

def get_wx_meteo(lat=0, lon=0, unit=0):
	# set forcast days 1 or 3
	forecastDays = 3

	# Make sure all required weather variables are listed here
	# The order of variables in hourly or daily is important to assign them correctly below
	url = "https://api.open-meteo.com/v1/forecast"
	params = {
		"latitude": {lat},
		"longitude": {lon},
		"daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_hours", "precipitation_probability_max", "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant"],
		"timezone": "auto",
		"forecast_days": {forecastDays}
	}

	# Unit 0 is imperial, 1 is metric
	if unit == 0:
		params["temperature_unit"] = "fahrenheit"
		params["wind_speed_unit"] = "mph"
		params["precipitation_unit"] = "inch"
		params["distance_unit"] = "mile"
		params["pressure_unit"] = "inHg"

	try:
		# Fetch the weather data
		weather_data = get_weather_data(url, params)
	except Exception as e:
		logger.error(f"Error fetching meteo weather data: {e}")
		return ERROR_FETCHING_DATA

	# Check if we got a response
	try:
		# Process location
		logger.debug(f"System: Pulled from Open-Meteo in {weather_data['timezone']} {weather_data['timezone_abbreviation']}")
		
		# Ensure response is defined
		response = weather_data
		
		# Process daily data. The order of variables needs to be the same as requested.
		daily = response['daily']
		daily_weather_code = daily['weather_code']
		daily_temperature_2m_max = daily['temperature_2m_max']
		daily_temperature_2m_min = daily['temperature_2m_min']
		daily_precipitation_hours = daily['precipitation_hours']
		daily_precipitation_probability_max = daily['precipitation_probability_max']
		daily_wind_speed_10m_max = daily['wind_speed_10m_max']
		daily_wind_gusts_10m_max = daily['wind_gusts_10m_max']
		daily_wind_direction_10m_dominant = daily['wind_direction_10m_dominant']
	except Exception as e:
		logger.error(f"Error processing meteo weather data: {e}")
		return ERROR_FETCHING_DATA

	# convert wind value to cardinal directions
	for value in daily_wind_direction_10m_dominant:
		if value < 22.5:
			wind_direction = "С"
		elif value < 67.5:
			wind_direction = "СВ"
		elif value < 112.5:
			wind_direction = "В"
		elif value < 157.5:
			wind_direction = "ЮВ"
		elif value < 202.5:
			wind_direction = "Ю"
		elif value < 247.5:
			wind_direction = "ЮЗ"
		elif value < 292.5:
			wind_direction = "З"
		elif value < 337.5:
			wind_direction = "СЗ"
		else:
			wind_direction = "С"

	# create a weather report
	weather_report = ""
	for i in range(forecastDays):
		if str(i + 1) == "1":
			weather_report += "Сегодня: "
		elif str(i + 1) == "2":
			weather_report += "Завтра: "
		else:
			weather_report += "Послезавтра: "
		
		# report weather from WMO Weather interpretation codes (WW)
		code_string = ""
		if daily_weather_code[i] == 0:
			code_string = "Ясно"
		elif daily_weather_code[i] == 1:
			code_string = "Облачно"
		elif daily_weather_code[i] == 2:
			code_string = "Перем. облачность"
		elif daily_weather_code[i] == 3:
			code_string = "Пасмурно"
		elif daily_weather_code[i] == 5:
			code_string = "Дымка"
		elif daily_weather_code[i] == 10:
			code_string = "Морось"
		elif daily_weather_code[i] == 45:
			code_string = "Туман"
		elif daily_weather_code[i] == 48:
			code_string = "Изморозь"
		elif daily_weather_code[i] == 51:
			code_string = "Легкая морось"
		elif daily_weather_code[i] == 53:
			code_string = "Морось"
		elif daily_weather_code[i] == 55:
			code_string = "Сильная морось"
		elif daily_weather_code[i] == 56:
			code_string = "Легкая ледяная морось"
		elif daily_weather_code[i] == 57:
			code_string = "Ледяная морось"
		elif daily_weather_code[i] == 61:
			code_string = "Легкий дождь"
		elif daily_weather_code[i] == 63:
			code_string = "Дождь"
		elif daily_weather_code[i] == 65:
			code_string = "Сильный дождь"
		elif daily_weather_code[i] == 66:
			code_string = "Легкий ледяной дождь"
		elif daily_weather_code[i] == 67:
			code_string = "Ледяной дождь"
		elif daily_weather_code[i] == 71:
			code_string = "Легкий снег"
		elif daily_weather_code[i] == 73:
			code_string = "Снег"
		elif daily_weather_code[i] == 75:
			code_string = "Сильный снег"
		elif daily_weather_code[i] == 77:
			code_string = "Снежная крупа"
		elif daily_weather_code[i] == 78:
			code_string = "Ледяные иглы"
		elif daily_weather_code[i] == 79:
			code_string = "Ледяной дождь"
		elif daily_weather_code[i] == 80:
			code_string = "Легкий ливень"
		elif daily_weather_code[i] == 81:
			code_string = "Ливень"
		elif daily_weather_code[i] == 82:
			code_string = "Сильный ливень"
		elif daily_weather_code[i] == 85:
			code_string = "Снежный ливень"
		elif daily_weather_code[i] == 86:
			code_string = "Сильный снежный ливень"
		elif daily_weather_code[i] == 95:
			code_string = "Гроза"
		elif daily_weather_code[i] == 96:
			code_string = "Гроза с градом"
		elif daily_weather_code[i] == 97:
			code_string = "Сильная гроза"
		elif daily_weather_code[i] == 99:
			code_string = "Сильная гроза с градом"

		weather_report += code_string + ". "

		# report temperature
		if unit == 0:
			weather_report += "Макс: " + str(int(round(daily_temperature_2m_max[i]))) + "F, мин: " + str(int(round(daily_temperature_2m_min[i]))) + "F. "
		else:
			weather_report += "Макс: " + str(int(round(daily_temperature_2m_max[i]))) + "C, мин: " + str(int(round(daily_temperature_2m_min[i]))) + "C. "

		# check for precipitation
		if daily_precipitation_hours[i] > 0:
			if unit == 0:
				weather_report += "Осадки: " + str(round(daily_precipitation_probability_max[i],2)) + "in, за " + str(round(daily_precipitation_hours[i],2)) + " ч. "
			else:
				weather_report += "Осадки: " + str(round(daily_precipitation_probability_max[i],2)) + "mm, за " + str(round(daily_precipitation_hours[i],2)) + " ч. "
		else:
			weather_report += "Без осадков. "

		# check for wind
		if daily_wind_speed_10m_max[i] > 0:
			if unit == 0:
				weather_report += "Ветер: " + str(int(round(daily_wind_speed_10m_max[i]))) + "mph, порывы до " + str(int(round(daily_wind_gusts_10m_max[i]))) + "mph с " + wind_direction + "."
			else:
				weather_report += "Ветер: " + str(int(round(daily_wind_speed_10m_max[i]))) + "kph, порывы до " + str(int(round(daily_wind_gusts_10m_max[i]))) + "kph с " + wind_direction + "."
		else:
			weather_report += "Без ветра. "

		# add a new line for the next day
		if i < forecastDays - 1:
			weather_report += "\n"

	return weather_report

def get_flood_openmeteo(lat=0, lon=0):
	# set forcast days 1 or 3
	forecastDays = 3

	# Flood data
	url = "https://flood-api.open-meteo.com/v1/flood"
	params = {
		"latitude": {lat},
		"longitude": {lon},
		"timezone": "auto",
		"daily": "river_discharge",
		"forecast_days": forecastDays
	}

	try:
		# Fetch the flood data
		flood_data = get_weather_data(url, params)
	except Exception as e:
		logger.error(f"Error fetching meteo flood data: {e}")
		return ERROR_FETCHING_DATA
	
	# Check if we got a response
	try:
		# Process location
		logger.debug(f"System: Pulled River FLow Data from Open-Meteo {flood_data['timezone_abbreviation']}")
		
		# Ensure response is defined
		response = flood_data
		
		# Process daily data. The order of variables needs to be the same as requested.
		daily = response['daily']
		daily_river_discharge = daily['river_discharge']
		# check if none

	except Exception as e:
		logger.error(f"Error processing meteo flood data: {e}")
		return ERROR_FETCHING_DATA
	
	# create a flood report
	flood_report = ""
	flood_report += "River Discharge: " + str(daily_river_discharge) + "m3/s"

	return flood_report
