import numpy as np
import pandas as pd
#import scikit-learn as sklearn
import matplotlib.pyplot as plt

#function to compute the total number of observations
#can be used to normalize the distribution to an empirical density
def totalObservationCounter(array):
    observations = 0
    for i in array:
        if  i == "noterad":
            observations += 1
        else:
            observations += int(i) 
    return observations 

#replace all "noterad" by a one 
#and convert all string numbers inot integers
def observationToInt(array):
    intObservations = np.ones(len(array))
    for i in range(len(array)):
        if array[i] == "noterad":
            continue
        else: 
            intObservations[i] = int(array[i])
    return intObservations
            

#strips all unnecessary information away and only keeps the month 
#expects format of "yyyy-mm-dd" (but would also work with "dd-mm-yyyy")
def extractMonth(array):
    monthArray = []
    for i in array:
        month = i.split('-')[1]
        monthArray.append(month)
    return np.array(monthArray) 

#function to compute the observations per month 
def computeObservationsPerMonth(monthArray, observationArray):
    observationsPerMonth = np.zeros(12)
    for i in range(len(monthArray)):
        observationsPerMonth[int(monthArray[i]) - 1] += observationArray[i]
    return observationsPerMonth

def computeEmpiricalDensity(inputPath):
    df = pd.read_csv(inputPath)
    x = extractMonth(df["Startdatum"])
    y = observationToInt(df["Antal"])
    totalObservation = totalObservationCounter(df["Antal"])
    observationsPerMonth = computeObservationsPerMonth(x, y)
    empiricalDensity = observationsPerMonth/totalObservation
    return empiricalDensity





#note that the extra information in the number of observed butterflys doesnt seem to change the distribution
#model idea: assume underlying probability density and approxamite it by empirical density function (observationsPerMonth/totalObservations)

#new idea: pca to find good predictors (but predictors for what??)

#another idea: scatter plot with geographical positions (bigger dots reprensent more sightings) and colour them according to specific (climate?) zones

empiricalDensityRovfjäril = computeEmpiricalDensity("./rovfjäril25.csv")
empricalDensityRapsfjäril = computeEmpiricalDensity("./raps.csv")

# plt.plot(empiricalDensityRovfjäril)
# plt.plot(empricalDensityRapsfjäril)

# observationsPerMonth = computeObservationsPerMonth
# plt.plot(observationsPerMonth)

#scatter plot showing the sightings on the 'map'
#plt.scatter(df["Ost"], df["Nord"])

df = pd.read_csv("./raps.csv")

months = extractMonth(df["Startdatum"]).astype(int)
sightings = observationToInt(df["Antal"])

df["month"] = months
df["sightings"] = sightings

lan_order = [
    "Skåne",
    "Blekinge",
    "Kalmar",
    "Halland",
    "Kronoberg",
    "Gotland",
    "Västra Götaland",
    "Jönköping",
    "Östergötland",
    "Södermanland",
    "Örebro",
    "Stockholm",
    "Västmanland",
    "Värmland",
    "Uppsala",
    "Dalarna",
    "Gävleborg",
    "Västernorrland",
    "Jämtland",
    "Västerbotten",
    "Norrbotten"
]

df["Län"] = pd.Categorical(
    df["Län"],
    categories=lan_order,
    ordered=True
)

grouped = (
    df.groupby(["Län", "month"], observed=True)["sightings"]
      .sum()
      .reset_index()
)

from matplotlib.colors import TwoSlopeNorm

norm = TwoSlopeNorm(vmin=0, vcenter=600, vmax=1700)

plt.scatter(
    grouped["month"],
    grouped["Län"],
    c=grouped["sightings"],
    cmap="YlOrRd",
    norm=norm
)

plt.colorbar(label="Number of sightings")
plt.xlabel("Month")
plt.ylabel("Län")
plt.show()