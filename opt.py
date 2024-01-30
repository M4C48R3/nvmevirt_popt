import skopt
import numpy as np
import os
import json
import datetime
import time
import sys
t = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=9)
TIME_STRING = t.strftime("%y%m%dT%H%M")

def objective(parameters):
	realdevid = None
	virtdevid = "/dev/nvme3n1"
	virtdevname = virtdevid.split("/")[-1]
	mod_install_script = "sudo insmod nvmev.ko memmap_start=12G memmap_size=40G cpus=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16"
	mod_uninstall_script = "sudo rmmod nvmev"

	# set parameters, and compile
	cmd = "sh -c \"./ssd_config_make.sh "
	cmd += " ".join(map(str,parameters))
	cmd += ("\"")
	print(cmd)
	os.system(cmd)
	os.system("make clean; make")

	results = {}
	results["read"] = {}
	results["write"] = {}
	results["parameters"] = ",".join(map(str,parameters))
	errors = []
	
	with open("./results/global_iteration_count.txt", "r+") as f:
		global_iteration_count = int(f.read())
		f.seek(0)
		f.write(str(global_iteration_count + 1))

	result_json = {}
	try:
		with open("./results/results.json") as f:
			result_json = json.load(f)
	except:
		result_json = {}

	# list test parameters (skip some blocksize or change test io size)
	#blocksizes = (4096,16384,65536,131072,262144)
	blocksizes = (4*1024,8*1024,16*1024,32*1024,64*1024,128*1024,256*1024)
	testsize = 2 * (2 ** 30) 

	#load module. attempt twice
	if os.system(mod_install_script) != 0:
		# wait and retry
		time.sleep(10)
		os.system(mod_uninstall_script)
		time.sleep(10)
		if os.system(mod_install_script) != 0:
			raise Exception("Module installation failed")
	
	# check if module is loaded
	time.sleep(3)
	if os.system(f"lsblk -d -o name,SERIAL | grep \"{virtdevname} CSL_Virt_SN_01\"") != 0:
		# wait and retry
		time.sleep(10)
		if os.system(f"lsblk -d -o name,SERIAL | grep \"{virtdevname} CSL_Virt_SN_01\"") != 0:
			raise Exception("Wrong virtual device route given")
	
	# -*- randread -*-
	actual = {4096: 62922, 8192: 76133, 16384: 86471, 32768: 104286, 65536: 136775, 131072: 197360, 262144: 284247} # U.2 Delta
	#actual = {4096: 92222, 8192: 98981, 16384: 120714, 32768: 176048, 65536: 278569, 131072: 416018, 262144: 484545}

	# sequential write before randread
	os.system(f"sudo fio --name=SW_before_RR --rw=write --bs=256k --iodepth=64 --runtime=40 --size={testsize} --numjobs=1 --direct=1 --filename={virtdevid} --output=/dev/null")
	 
	for bs in blocksizes:
		os.system(f"sudo fio --name=RR_{bs} --minimal --rw=randread --bs={bs} --iodepth=1 --size={testsize} --numjobs=1 --direct=1 --filename={virtdevid} "
		f"--runtime=15 --startdelay=1 --output-format=json --output=./results/{bs}.json")
		f = open(f"./results/{bs}.json")
		v = json.load(f)["jobs"][0]["read"]["lat_ns"]["mean"]
		errors.append(abs(actual[bs] - v) / actual[bs])
		results["read"][bs] = v
		f.close()

	# # -*- randwrite -*-
	actual = {4096: 11562, 8192: 12401, 16384: 14104, 32768: 17441, 65536: 24017, 131072: 41893, 262144: 81964} # U.2 Delta
	#actual = {4096: 16295, 8192: 18048, 16384: 22005, 32768: 32092, 65536: 50065, 131072: 90915, 262144: 165590} 

	offset = testsize
	for bs in blocksizes:
		os.system(f"sudo fio --name=RW_{bs} --minimal --rw=randwrite --bs={bs} --iodepth=1 --size={testsize} --numjobs=1 --direct=1 --filename={virtdevid} "
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
		print("\nScore: %.3f + %.3f = %.3f" %(score_avg, score_max, score_avg + score_max))

	# write results to json
	result_json[global_iteration_count] = results
	resf = open("./results/results.json", "w")
	json.dump(result_json, resf)
	resf.close()

	# flush stdout
	sys.stdout.flush()
	
	return (score_avg + score_max)


# define search space. [-1,value] to leave as constant
space = [
	[1024,2048], # NAND_CHANNEL_BANDWIDTH (MB/s)
	[-1,6800], # PCIE_BANDWIDTH
	[1e4,7e4], # 4KB_READ_LATENCY (ns)
	[1e4,7e4], # READ_LATENCY
	[-1, 1.85e6], # PROG_LATENCY and ERASE_LATENCY
	[1e3, 2e4], # FW_4KB_READ_LATENCY
	[1e3, 2e4], # FW_READ_LATENCY
	[1e3, 1e4], # FW_WBUF_LATENCY0
	[0, 500], # FW_WBUF_LATENCY1
	[0, 3000], # FW_CH_XFER_LATENCY
	[-1, 65536], # GLOBAL_WB_SIZE (KB) <- Do not set it too low, should be at least MDTS-sized (MDTS=8, >=1MB)
]

# define search space. [-1,value] to leave as constant
# space = [
# 	[-1,600], # NAND_CHANNEL_BANDWIDTH (MB/s)
# 	[-1,3400], # PCIE_BANDWIDTH
# 	[-1, 74e3], # 4KB_READ_LATENCY (ns)
# 	[-1, 74e3], # READ_LATENCY
# 	[-1, 2.32e6], # PROG_LATENCY and ERASE_LATENCY
# 	[-1, 5e3], # FW_4KB_READ_LATENCY
# 	[-1, 5e3], # FW_READ_LATENCY
# 	[5000, 3e4], # FW_WBUF_LATENCY0
# 	[300, 3e3], # FW_WBUF_LATENCY1
# 	[0, 4e3], # FW_CH_XFER_LATENCY
# 	[1536, 6144], # GLOBAL_WB_SIZE (KB) <- Do not set it too low, should be at least MDTS-sized (MDTS=8, >=1MB)
# ]

def objective_opt(opt_parameters):
	parameters = []
	opt_param_index = 0
	for i in range(len(space)):
		if space[i][0] == -1:
			parameters.append(np.int64(space[i][1]))
		else:
			parameters.append(opt_parameters[opt_param_index])
			opt_param_index += 1
	return objective(parameters)

def skopt_dim(space_ends):
	dimensions = []
	for i in range(len(space_ends)):
		if space[i][0] != -1:
			dimensions.append(skopt.space.space.Integer(space[i][0], space[i][1]))
	return dimensions
# run optimization

if __name__ == "__main__":
	checkpoint_file = f"./results/checkpoint_{TIME_STRING}.pkl"
	LOAD = None #"./results/checkpoint_240109T1707.pkl"# put file to load (./output/checkpoints/checkpoint 1691380588.pkl), if not loading a previous result from a file, set to 0
	res = skopt.load(LOAD) if LOAD else None
	res = skopt.optimizer.gp_minimize(
		func=objective_opt, dimensions=skopt_dim(space),
		initial_point_generator="hammersly", n_calls=100, n_initial_points=0 if LOAD else 15,
		verbose=True, callback=[skopt.callbacks.CheckpointSaver(checkpoint_file)],
		x0=res.x_iters if LOAD else None, y0=res.func_vals if LOAD else None
	)
	print(res)
#objective([1600,6900,40e3,50e3, 1.85e6, 15e3, 15e3, 6500, 300, 300, 64*1024]) # test
#objective([1150,3400,68e3,85e3, 3.7e6, 15e3, 15e3, 13500, 210, 2500, 8*1024])
#objective([600,3400,73849,73849,3700000,5000,5000,13604,400,3000,4839]) # Bravo (PCIe 3.0), with write performace at 1118 (actual SSD shows ~1700 for first 20GB and drops over time to 700-800) 
#objective([600,3400,73849,73849,2320000,5000,5000,13500,1000,3000,3072]) # Bravo (PCIe 3.0)
#objective([640,3400,72954,74818,3300000,8451,5672,9783,1012,3500,6144]) # Bravo (PCIe 3.0) final (94787.97149	104891.1555	126750.5763	165749.4968	268856.183	421172.5125	478005.0972	15657.13749	18255.62594	22765.9218	32141.91129	50156.31784	86672.0813	159876.7153)
#objective([1775,6800,42867,44302,1850000,12764,20000,7346,113,1314,65536]) # Delta (PCIe 4.0)