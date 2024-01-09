#include <iostream>
#include <string>
#include <stdio.h>
#include <fstream>
#include <chrono>
#include <unistd.h>
#include <getopt.h>

struct options {
	int runtime = -1;
	int size = -1;
	int delay = -1;
	std::string devname = "";
	std::string outputfile = "";
};

void ProcessArgs(int argc, char** argv, struct options opt){
	
}

int main(int argc, char* argv[]){
	using namespace std;
	int opt;

	while((opt = getopt()))
}