@echo off
set agent1=rule15/main.py
set agent2=rule16/main.py
set num_loops=1000
SetLocal EnableDelayedExpansion

echo start %DATE% %TIME% > results.log
FOR /L %%G IN (1,18,%num_loops%) DO (
	echo|set /p="!TIME! %%G a" >> results.log
	lux-ai-2021 --seed %%G --loglevel 1 %agent1% %agent2% | grep "rank: 1" >> results.log  
	echo|set /p="!TIME! %%G b" >> results.log
	lux-ai-2021 --seed %%G --loglevel 1 %agent2% %agent1% | grep "rank: 1" >> results.log  	
)

echo end %DATE% %TIME% >> results.log

echo|set /p="%agent1% win " >> results.log
grep --count %agent1% results.log | tee -a results.log

echo|set /p="%agent2% win " >> results.log
grep --count %agent2% results.log | tee -a results.log