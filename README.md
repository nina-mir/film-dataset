# scale-hackathon-april-20

## Big Idea
A chatbot that allows interaction with a publicly available dataset of film/TV projects filmed in San Francisco city over the past 100 years. 
The augmented dataset is publicly available on SFgov.data as a CSV file. 

Keywords: RAG, films, history, San Francisco

### Data

The dataset for this project can be previewed [here](https://data.sfgov.org/Culture-and-Recreation/Film-Locations-in-San-Francisco/yitu-d5am/data_preview).
The current dataset was last updated by the SF's Film Commission on March 13, 2024. More info about the data can be found on [http://www.filmsf.org/](	http://www.filmsf.org/). 
The raw data contains 2084 row with 13 columns:

**Title**	| **Release Year** | **Locations**	|**Fun Facts** | **Production Company** | **Distributor**	| **Director** | **Writer** | **Actor 1** | **Actor 2** | **Actor 3**

For this work, an abridged dataset containing the following column data is created: 

**Title**	| **Release Year** | **Locations**	| **Fun Facts** | **Director** | **Writer** | **Actor 1** | **Actor 2** | **Actor 3** 
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
