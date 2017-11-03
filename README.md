# account-analysis

A repo for an application allowing to aggregate credit card expenses with the expenditure type and location, in order to categorize each expenditure on a statement with a location and a type.

This is an ongoing development project with updates to follow for visulaisation and aggregation of data.

## What you will Need:
- A Google API key
- User location data from Google takeout
- CSV files from credit card data
- SQLite (code to be added soon for DB initialization)

## Implementation
My method to achieve mapping type and location to an expenditure was to use the credit card statement to derive the companies name and then I used my phones location (downloaded straight from Google) to then map approximate locations to these expenses.  Then based on an approximate location and the companies name where I spent the money I queried Google's Places API in order to find establishments matching the criteria.  Now sounds simple, but turned out to be a bit more involved to get good accuracy.
This was for two primary problems firstly descriptions in credit card statements are ambiguous (they rarely just state the companies name), secondly an expense is logged by day with no time associated with it, so which of the on average 100 locations which Google logged me at per day (yes, over 6 months I had about 120 000 distinct coordinates, quite scary).  
There are of course further problems like, what to do for online companies, what to do for companies with numerous establishments there are quite a few Peet's in San Francisco.  Before I delve into the details I would just like to grind a gear, that all this inherent data, exact location and type of business, is in the systems of the banks, it is quite infuriating not to have this on my statement.  This seems like a lot of effort just to record and track my expenses.


## Description of Methods

#### Company Name Extraction (descriptionparser.py)
This is a method to extract a company name from the description on a bank statement.  Example given below:
[example parse](/assets/photos/example_parse.png)

The method is currently a rule based method with the heuristics outlined below.  This will in the near future, once a corpus of training material is made, be augmented into a Naive Bayes approach.
- For each description tokenize the word and score each word for its likelihood of being part of the companies name
- Inspect the length of the word, if longer that 5 letters it is more likely to be a word.
- Check if the word is in the dictionary (+1 point).  It is at least a word.
- Check if there are any embedded words in tokens longer than three letters.  A token is more likely to represent a word if it in fact does itself contain a word, and if it is an actual word then it is more likely to form part of the companies name.
- Previous word frequency, common expenses for example Starbucks may appear on the statement as such "Starbucks z0Jan17" but the word Starbucks will have a higher frequency if I have often gone to Starbucks.  The noise around the companies name will change but the name will be the constant.
- Previous phonetics, now this is less important for company name identification, but is more important in the disambiguation.  I use fuzzy with dmetaphone to create a phonetic representation for each word and see how often that phonetics occur.  Actually using phonetics is quite useful as for example AMZ = Amazon and there 3 character phonetic representation is the same and often when it comes to looking for acronyms we look for phonetic similarity.
- Word structure, how many vowels and consonants, a token with 2 or more vowels and more consonants is more likely to represent a word.

##### Disambiguation
At this step after step one you have the predicted company name, but this could have multiple representations for the same company i.e. AMZ, Amazon, Amazon eu
In order to relate these and its variants together I used a number of techniques and if all 3 conditions were satisfied the company was declared a subset of the others:
- Phonetic representation, I looked at the phonetic representation of the first word and see if this matches any other in the company list.
- Check if all the letters of one companies name is in the others, for example {A,M,Z} intersects {A,M,Z,O,N} - Amazon.
- Check if the first letter is the same.  Simple but pretty important.


#### Location of the expenses (company_type.py)
Google Places API is used to derive the company type (shopping, food...), as well as a database of predefined companies and their type.  In order to use Google API a query needs to be fed in.  In essence for the google query I need to feed in a location and a company name.  Now the problem is that my google locations file contains maybe a hundred visited locations on a given day.  So what I do (and this is crude, I wish to implement possibly a k-means approach) is I pick from the database of visited location for the day of the expense, one distinct location (this should hopefully give me at least the city I am in).
I send this along with the predicted companies name to google.  Now google responds with a json, with a number of results matching my query.  I take the results of this each of which is a distinct company with GPS coordinates, and I calculate an array with each possible company and its distance to each of the locations I visited on the day of the expense.  This means that hopefully if Google has done a good job of tracking me then when I look for the smallest distance it will likely be the location I visited.

## Improvements to Make
- Include name matching heuristic for parsing the google search query so both distance and name similarity are used for business match evaluation.
- Naive Bayes' model for company name extraction.
- Visualisation Dashboard (ongoing)
