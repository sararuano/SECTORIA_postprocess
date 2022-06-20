# -*- coding: utf-8 -*-
"""
PROJECT: SECTORIA Configuration Optimizer Post-processing Tool
DATE: 06-04-2022
DESCRIPTION: This project is the post-processing tool for the configuration optimizer developed in CRIDA, SECTORIA. 

AUTHOR: Sara Ruano Ferrer

"""

import pandas as pd
import numpy as np
from datetime import datetime
from datetime import timedelta

#Initial read SECTORIA output
file=pd.read_csv('output.csv', sep=',')
results=pd.read_csv('output.csv', sep=',', usecols=[0], names=['time'])

#INPUT PARAMETERS

number_solutions=(len(file.columns)-1)/3
window_time=20
minimum_nochange_time=60

#Read SECTORIA output and list all configurations
i=1
configurations=pd.DataFrame(columns=['Sectors'])
while i<=number_solutions:
    results2=pd.read_csv('output.csv', sep=',', usecols=[3*i-2, 3*i-1, 3*i], names=['configuration'+str(i), 'cost'+str(i), 'capacity'+str(i)])
    configurations2=pd.DataFrame(results2['configuration'+str(i)].unique(), columns=['Sectors'])
    if(i>1):
        configurations=configurations.append(configurations2, ignore_index=True)
    else:
        configurations=configurations2
    results=results.join(results2)
    i+=1

configurations=pd.DataFrame(configurations.Sectors.unique(), columns=['Sectors'])
configurations.reset_index(inplace=True)
configurations=configurations.rename(columns={'index':'configuration_index'})


#the following function computes the number of sectors a configuration has
def ComputeNumberSectors(sectors):
    num_sectors=1
    for character in str(sectors):
        if(character=='+'):
            num_sectors+=1
    return num_sectors

configurations['NumberSectors']=configurations['Sectors'].apply(lambda x: ComputeNumberSectors(x))


def GetTimes(times):
    times=str(times)
    initialTime=times[0:2]+':'+times[2:4]
    initialTime=datetime.strptime(initialTime+':00', '%H:%M:%S')
    
    finalTime=times[5:7]+':'+times[7:9]
    finalTime=datetime.strptime(finalTime+':00', '%H:%M:%S')
    
    return initialTime, finalTime

results['initialTime']=results['time'].apply(lambda x: GetTimes(x))
results['finalTime']=results[['initialTime']].apply(lambda x: x[0][1], axis=1)
results['initialTime']=results[['initialTime']].apply(lambda x: x[0][0], axis=1)

output=pd.DataFrame()
output['TStart']=results['initialTime']
output['TEnd']=results['finalTime']


#change of day for the last proposed configurations
i=1
while (i<60/window_time+1):
    output.loc[len(output)-i, 'TEnd']=output.loc[len(output)-i, 'TEnd']+timedelta(days=1)
    i+=1

i=1
while(i<=number_solutions):
    output['Sectors']=results['configuration'+str(i)]
    output=output.join(configurations.set_index('Sectors'), on='Sectors')
    output=output.rename(columns={'Sectors':'Sectors'+str(i), 'configuration_index':'configuration_index'+str(i), 'NumberSectors':'NumberSectors'+str(i)})
    i+=1

#function to obtain all the cuts at all the sectors of the configuration
def GetCutsInConfig(configuration):
    if isinstance(configuration, str) :
        sectorsInConfig=configuration.split('+')
        Ruta=pd.DataFrame(sectorsInConfig, columns=['sectorsInConfig'])
        Ruta['sectorElemental']=Ruta['sectorsInConfig'].apply(lambda x: x[4:7])
        Ruta['hayquecortar']=Ruta['sectorElemental'].apply(lambda x: x.endswith('I') or x.endswith('L') or x.endswith('2') or x.endswith('4') or x.endswith('6') or x.endswith('8'))
        def Cut(sector, hayquecortar):
            if hayquecortar:
                return sector[0:2]
            else:
                return sector
    else:
        return 'void_configuration'
        
    Ruta['sectorElemental']=Ruta[['sectorElemental','hayquecortar']].apply(lambda x: Cut(x['sectorElemental'], x['hayquecortar']), axis=1)
    Ruta.drop(columns=['hayquecortar'], inplace=True)
    Ruta.loc[Ruta['sectorElemental']=='LEC', 'sectorElemental']='LECMR1'
    
    def DeterminarCorte(sector):
        if(sector.endswith('I') or sector=='LECMR1' or sector=='LECMSAN' or sector=='LECMBDP'):
            return 'Integrado'
        elif(sector.endswith('U')):
            return 'FL3' + sector[-2]+'5'
        elif(sector[-2]=='L'):
            return 'FL3' + sector[-1]+'5'
        else:
            return 'NoIntegrado'
        
    Ruta['Corte']=Ruta['sectorsInConfig'].apply(lambda x: DeterminarCorte(x))
    Cuts=pd.DataFrame(Ruta.sectorElemental.unique(), columns=['sectores'])
    
    def LookForCutsInRuta(sectorElemental):
        value=Ruta['Corte'][Ruta['sectorElemental']==sectorElemental]
        return value.iloc[0]
    Cuts['cut']=Cuts['sectores'].apply(lambda x: LookForCutsInRuta(x))
    return Cuts


configurations['Cuts']=configurations['Sectors'].apply(lambda x: GetCutsInConfig(x))

initialscheme=pd.DataFrame(columns=['time', 'possibleConfig'])

initialscheme['time']=pd.date_range('1/1/1900', periods=24*(60/window_time), freq=str(window_time)+'min')

def LookForValuesInConfiguration(sectors, configurations):
    value=configurations['NumberSectors'][configurations['Sectors']==sectors]
    return value.iloc[0]
def LookForCutsInConfiguration(sectors, configurations):
    value=configurations['Cuts'][configurations['Sectors']==sectors]
    return value.iloc[0]   

#the following function computes the cost a certain configuration change implies, taking into account the changes in vertical cuts
def ComputeCostInChange(configuration, lastConfig, configurations):
    cost=0
    Cutsinconf=LookForCutsInConfiguration(configuration, configurations)
    Cutsinlastconf=LookForCutsInConfiguration(lastConfig, configurations)
    Cutsinconf=Cutsinconf.merge(Cutsinlastconf, on='sectores', how='outer')
    Cutsinconf['aretheythesame']=Cutsinconf.iloc[:,1]==Cutsinconf.iloc[:,2]
    cost=len(Cutsinconf[Cutsinconf['aretheythesame']==False])
    return cost


#the following function selects the proposed configuration in a time interval with the minimal number of sectors, or mantaining the same cofiguration selected in the previous interval
def GetBestConfiguration(time, lastconfiguration, output, configurations, timeSinceLastChange):
    #we get the obtained configurations in different time periods included in the studied time
    initial_possible_configurations=output[(output.TStart<=time) & (output.TEnd>time)]
    possible_configurations=pd.DataFrame()
    i=1 
    while(i<=number_solutions):
        possible_configurations2=pd.DataFrame(initial_possible_configurations['Sectors'+str(i)].unique(), columns=['Sectors'])
        possible_configurations=possible_configurations.append(possible_configurations2)
        i+=1
    possible_configurations=pd.DataFrame(possible_configurations.Sectors.unique(), columns=['Sectors'])
    possible_configurations=possible_configurations.dropna()
    possible_configurations['NumberSectors']=possible_configurations['Sectors'].apply(lambda x: LookForValuesInConfiguration(x, configurations))
    
    minimum_timesincelastchange=minimum_nochange_time/window_time+1
    if timeSinceLastChange<=minimum_timesincelastchange and lastconfiguration in possible_configurations['Sectors'].tolist():
        #if less than 40 minutes ago (this time can be chosen) the configuration has been changed, it cannot be changed again if the previous configuration is available
        suggested_configuration=lastconfiguration
    else:    
        #the minimum-sector configuration or, as far as possible, the previous configuration is selected
        minimum_sector_conf=possible_configurations[possible_configurations.NumberSectors==possible_configurations.NumberSectors.min()]
        minimum_sector_conf=minimum_sector_conf.reset_index()
        #check if one of the proposed configurations is the same as the pevious one 
        minimum_sector_conf['IsLastConfiguration']=minimum_sector_conf.Sectors==lastconfiguration

        same_as_last_conf=minimum_sector_conf[minimum_sector_conf.IsLastConfiguration==True]
        same_as_last_conf.reset_index(inplace=True)

        suggested_configuration=[]
        if(len(same_as_last_conf)>0):
            #if the previous configuration is within the offered ones, it is the chosen one
            suggested_configuration=same_as_last_conf.loc[0,'Sectors']
        else:
            #if the previous configuration is not available, the minimum-cost change is chosen
            minimum_sector_conf['Cost']=minimum_sector_conf['Sectors'].apply(lambda x: ComputeCostInChange(x, lastconfiguration, configurations))        
            minimum_sector_conf=minimum_sector_conf.loc[minimum_sector_conf['Cost']==minimum_sector_conf['Cost'].min(),'Sectors']
            suggested_configuration=minimum_sector_conf.iloc[0]
    return suggested_configuration

#iterate along the day to compute the initial scheme
lastconfig='LECMR1I'
timeSinceLastChange=0
for i, row in initialscheme.iterrows():
    lastconfig2=GetBestConfiguration(row.time, lastconfig, output, configurations, timeSinceLastChange)
    if(lastconfig2==lastconfig):
        timeSinceLastChange+=1
    else:
        timeSinceLastChange=0
    lastconfig=lastconfig2
    initialscheme.loc[i, 'possibleConfig']=lastconfig
    
      
    
initialscheme.to_csv('INITIALSCHEME.csv', index=False)
