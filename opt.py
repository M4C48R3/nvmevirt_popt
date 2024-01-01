import skopt
import numpy as np
import os
import json
import datetime

t = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=9)
TIME_STRING = t.strftime("%y%m%dT%H%M")

def objective(parameters):
	realdevid = None
	virtdevid = "/dev/nvme2n1"
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
	testsize = 3 * (2 ** 30) 

	# -*- randread -*-
	#actual = {4096: 62922, 8192: 76133, 16384: 86471, 32768: 104286, 65536: 136775, 131072: 197360, 262144: 284247} # U.2 Delta
	actual = {4096: 93316, 8192: 100216, 16384: 121761, 32768: 176205, 65536: 276317, 131072: 417107, 262144:485448}

	# sequential write before randread
	os.system(mod_install_script)
	os.system(f"sudo fio --name=SW_before_RR --rw=write --bs=256k --iodepth=64 --runtime=40 --size={testsize} --numjobs=1 --direct=1 --filename={virtdevid} --output=/dev/null")
	 
	for bs in blocksizes:
		os.system(f"sudo fio --name=RR_{bs} --minimal --rw=randread --bs={bs} --iodepth=1 --size={testsize} --numjobs=1 --direct=1 --filename={virtdevid} "
		f"--runtime=20 --output-format=json --output=./results/{bs}.json")
		f = open(f"./results/{bs}.json")
		v = json.load(f)["jobs"][0]["read"]["lat_ns"]["mean"]
		errors.append(abs(actual[bs] - v) / actual[bs])
		results["read"][bs] = v
		f.close()

	# # -*- randwrite -*-
	#actual = {4096: 11562, 8192: 12401, 16384: 14104, 32768: 17441, 65536: 24017, 131072: 41893, 262144: 81964} # U.2 Delta
	actual = {4096: 18370, 8192: 20293, 16384: 24479, 32768: 32898, 65536: 50038, 131072: 108308, 262144: 241707} 

	offset = testsize
	for bs in blocksizes:
		os.system(f"sudo fio --name=RW_{bs} --minimal --rw=randwrite --bs={bs} --iodepth=1 --size={testsize} --numjobs=1 --direct=1 --filename={virtdevid} "
		f"--offset={offset} --startdelay=2 --runtime=30 --output-format=json --output=./results/{bs}.json")
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
			print(e, end=", ")
		print("Score: %f + %f = %f" %(score_avg, score_max, score_avg + score_max))

	# write results to json
	result_json[global_iteration_count] = results
	resf = open("./results/results.json", "w")
	json.dump(result_json, resf)
	resf.close()
	
	return (score_avg + score_max)


# define search space. [-1,value] to leave as constant
space = [
	[600,1100], # NAND_CHANNEL_BANDWIDTH (MB/s)
	[-1,3400], # PCIE_BANDWIDTH
	[3e4,12e4], # 4KB_READ_LATENCY (ns)
	[3e4,14e4], # READ_LATENCY
	[-1, 3.7e6], # PROG_LATENCY and ERASE_LATENCY
	[5e3, 5e4], # FW_4KB_READ_LATENCY
	[5e3, 5e4], # FW_READ_LATENCY
	[5e3, 2e4], # FW_WBUF_LATENCY0
	[100, 1e3], # FW_WBUF_LATENCY1
	[0, 3e3], # FW_CH_XFER_LATENCY
	[2048, 16384], # GLOBAL_WB_SIZE (KB) <- Do not set it too low, should be at least MDTS-sized (MDTS=8, >=1MB)
]

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

# if __name__ == "__main__":
# 	checkpoint_file = f"./results/checkpoint_{TIME_STRING}.pkl"
# 	LOAD = "./results/checkpoint_240101T1802.pkl"# put file to load (./output/checkpoints/checkpoint 1691380588.pkl), if not loading a previous result from a file, set to 0
# 	res = skopt.load(LOAD) if LOAD else None
# 	res = skopt.optimizer.gp_minimize(
# 		func=objective_opt, dimensions=skopt_dim(space),
# 		initial_point_generator="random", n_calls=50, n_initial_points=0,
# 		verbose=True, callback=[skopt.callbacks.CheckpointSaver(checkpoint_file)],
# 		x0=res.x_iters if LOAD else None, y0=res.func_vals if LOAD else None
# 	)
# 	print(res)
#objective([1600,6900,37e3,46e3, 1.85e6, 15e3, 15e3, 6500, 200, 80, 64*1024]) # test
#objective([1150,3400,68e3,85e3, 3.7e6, 15e3, 15e3, 13500, 210, 2500, 8*1024])
objective([600,3400,73849,73849,3700000,5000,5000,13604,400,3000,4839]) # Bravo (PCIe 3.0)