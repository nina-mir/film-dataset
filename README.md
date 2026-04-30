# NLP-2-GeoPandasDataFrame-Code via a 6-step-data-pipeline inpsired by a basic compiler design

> 3 of the steps are LLM-powered (using Gemini Flash-model-3 at this moment.)

## Big Idea
A chatbot that allows interaction with a publicly available dataset of film/TV projects filmed in San Francisco city over the past 100 years. 
The augmented dataset is publicly available on SFgov.data as a CSV file. 

## Backstory 
The idea for this project began as a motivation for me to learn RAG but soon, it turned out RAG is not capable of delivering accurate results for this dataset. Therefore, an idea of a proto agent came about. This data pipeline is, indeed, a custom, basic agent that is capable to conerting single-task user queries to accurate python code to be used agains the GeoPandasDataFrame dataset. 

**Current Focus:** Improving the resulting code for multi-intent user queries. 

**Keywords**: _agentic datapipeline, films, history, San Francisco_

## Data
### April-2026 update
#### Current Data Stats 
```python
Final shape:        (2208, 14)
CRS:                EPSG:4326
Geometry null:      86
Neighborhood null:  144
Unique films:       352

Column dtypes:
Title                    object
Year                      Int64
Locations                object
Fun_Facts                object
Production_Company       object
Distributor              object
Director                 object
Writer                   object
Actor_1                  object
Actor_2                  object
Actor_3                  object
Neighborhood             object
Supervisor_District       Int64
geometry               geometry

Top 10 neighborhoods (by row count):
Neighborhood
Financial District/South Beach    299
North Beach                       202
Chinatown                         163
Nob Hill                          163
Mission                           153
NaN                               144
Tenderloin                        138
Castro/Upper Market                88
Russian Hill                       86
South of Market                    80

Sample row (with geometry):
  Title: Milk
  Year: 2008
  Locations: El Camino Del Mar
  Fun_Facts: nan
  Production_Company: Focus Features
  Distributor: Focus Features
  Director: Gus Van Sant
  Writer: Dustin Lance Black
  Actor_1: Sean Penn
  Actor_2: Emile Hirsch
  Actor_3: nan
  Neighborhood: Lincoln Park
  Supervisor_District: 1
  geometry: POINT (-122.4962354 37.7857806)
```
### 2024 update
#### original data

The dataset for this project can be previewed [on SF government website.](https://data.sfgov.org/Culture-and-Recreation/Film-Locations-in-San-Francisco/yitu-d5am/data_preview).
The dataset downloaded for this project was last updated by the SF's Film Commission on March 13, 2024. More info about the data can be found on [http://www.filmsf.org/](	http://www.filmsf.org/). 
The raw data contains 2084 row with 14 columns:

` Title	| Release Year | Locations |Fun Facts | Production Company | Distributor | Director | Writer | Actor 1 | Actor 2 | Actor 3 | 
SF Find Neighborhoods | Analysis Neighborhoods | Current Supervisor Districts `

#### cleaned data used in this project

For this work, an abridged dataset containing the following 5 columns is created: 

```Title | Release Year | Locations | Director | Actor 1```

More info including the python script used to clean/abridge the dataset can be found in this repo's [```/data```](/data/readme.md) directory.

> [!NOTE]  
> Each row contains only one location data. Therefore, each film could have more than one location data associated with it. 


### Basic Features
The user could interact in a number of ways. Some examples are provided below:  
- list the moview shot in the 80s in San Francisco in alaphabetical order
- list the movies shot in the Mission distrcity
- How many films were shot near Embarcadero area of SF?
- What are some films shot in SF's Chinatown?
- What actors were part of more than 5 projects shot in San Francisco? 


### Ultimate Features

- Given my address of 1112 Bryant St, San Francisco CA 94110, what are some movie locations in a 1 mile radious from my address?


### Challenges

- The dataset is is a single CSV file with more than
