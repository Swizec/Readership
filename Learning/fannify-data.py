
# get data from mongo and output something FANN enjoys

# The first line consists of three numbers: The first is the number of training pairs in the file, the second is the number of inputs and the third is the number of outputs.  The rest of the file is the actual training data, consisting of one line with inputs, one with outputs etc.

from pymongo import Connection
import random

def extract(datapoint, keys):
    return reduce(list.__add__,
                  [val if type(val) == list else [val]
                   for k in keys
                   for (key,val) in datapoint[k].items()])

def inputs(datapoint):
    return extract(datapoint, ['style', 'length', 'complexity'])

def outputs(datapoint):
    return extract(datapoint, ['readership'])

def store(datapoints, filename):
    f = open(filename, 'w')

    f.write(str(len(datapoints))+" 14 "+" 2\n")
    for datapoint in datapoints:
        f.write(" ".join(map(str, inputs(datapoint)))+"\n")
        f.write(" ".join(map(str, outputs(datapoint)))+"\n")

    f.close()

if __name__ == "__main__":
    db = Connection().readership_data
    readership = db.readership

    datapoints = list(readership.find())
    random.shuffle(datapoints)

    # 70% training, 30% testing
    store(datapoints[:int(len(datapoints)*0.7)],
          "./training.dat")
    store(datapoints[int(len(datapoints)*0.7):],
          "./test.dat")
