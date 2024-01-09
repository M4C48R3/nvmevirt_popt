import skopt
import numpy as np
import os
import json
import datetime
import time
from sys import argv

t = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=9)
TIME_STRING = t.strftime("%y%m%dT%H%M")

def objective(parameters):
	dev_id = "/dev/nvme1n1"

	results = {}
	results["read"] = {}
	results["write"] = {}

	blocksizes = (4*1024,8*1024,16*1024,32*1024,64*1024,128*1024,256*1024)
	testsize = 8 * (2 ** 30) 
	errors = []

	# -*- randread -*-
	#actual = {4096: 62922, 8192: 76133, 16384: 86471, 32768: 104286, 65536: 136775, 131072: 197360, 262144: 284247} # U.2 Delta
	actual = {4096: 92222, 8192: 98981, 16384: 120714, 32768: 176048, 65536: 278569, 131072: 416018, 262144: 484545}

	# sequential write before randread
	os.system(f"sudo fio --name=SW_before_RR --rw=write --bs=256k --iodepth=64 --runtime=40 --size={testsize} --numjobs=1 --direct=1 --filename={dev_id} --output=/dev/null")
	 
	for bs in blocksizes:
		os.system(f"sudo fio --name=RR_{bs} --minimal --rw=randread --bs={bs} --iodepth=1 --size={testsize} --numjobs=1 --direct=1 --filename={dev_id} "
		f"--runtime=15 --startdelay=1 --output-format=json --output=./results/read_{bs}_{TIME_STRING}.json")
		f = open(f"./results/{bs}.json")
		v = json.load(f)["jobs"][0]["read"]["lat_ns"]["mean"]
		errors.append(abs(actual[bs] - v) / actual[bs])
		results["read"][bs] = v
		f.close()

	# # -*- randwrite -*-
	#actual = {4096: 11562, 8192: 12401, 16384: 14104, 32768: 17441, 65536: 24017, 131072: 41893, 262144: 81964} # U.2 Delta
	actual = {4096: 16295, 8192: 18048, 16384: 22005, 32768: 32092, 65536: 50065, 131072: 90915, 262144: 165590} 

	offset = testsize
	for bs in blocksizes:
		os.system(f"sudo fio --name=RW_{bs} --minimal --rw=randwrite --bs={bs} --iodepth=1 --size={testsize} --numjobs=1 --direct=1 --filename={dev_id} "
		f"--offset={offset} --startdelay=2 --runtime=20 --output-format=json --output=./results/{bs}.json")
		offset += testsize
		f = open(f"./results/{bs}.json")
		v = json.load(f)["jobs"][0]["write"]["lat_ns"]["mean"]
		errors.append(abs(actual[bs] - v) / actual[bs])
		results["write"][bs] = v
		f.close()
	os.system(mod_uninstall_script)

	score_avg = sum(errors) / len(errors)
	score_max = max(errors) / 2
	results["score"] ={}
	results["score"]["avg"] = score_avg
	results["score"]["max"] = score_max
	results["score"]["total"] = score_avg + score_max

	if True: # print results
		print("Results of iteration %d" % global_iteration_count)
		for bs in blocksizes:
			print("%d %d %d" % (bs, results["read"][bs], results["write"][bs]))
		print("Errors:")
		for e in errors:
			print("%.3f" %(e), end=", ")
		print("Score: %.3f + %.3f = %.3f" %(score_avg, score_max, score_avg + score_max))

	# write results to json
	result_json[global_iteration_count] = results
	resf = open("./results/results.json", "w")
	json.dump(result_json, resf)
	resf.close()
	
	return (score_avg + score_max)

