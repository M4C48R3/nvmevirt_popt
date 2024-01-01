# attempts=1
# max_attempts=600
# while [ $attempts -le $max_attempts ]
# do
#         echo "*-* $attempts *-*"
#         make clean
#         make
#         sudo rmmod nvmev
#         sudo insmod nvmev.ko memmap_start=12G memmap_size=40G cpus=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16
#         sudo fio --filename=/dev/nvme2n1 --direct=1 --rw=write --bs=64k --size=3G --name=a;
#         attempts=$((attempts+1))
# done