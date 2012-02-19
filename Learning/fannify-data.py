
# get data from mongo and output something FANN enjoys

# The first line consists of three numbers: The first is the number of training pairs in the file, the second is the number of inputs and the third is the number of outputs.  The rest of the file is the actual training data, consisting of one line with inputs, one with outputs etc.

from pymongo import Connection

def extract(datapoint, keys):
    return reduce(list.__add__,
                  [val if type(val) == list else [val]
                   for k in keys
                   for (key,val) in datapoint[k].items()])

def inputs(datapoint):
    return extract(datapoint, ['style', 'length', 'complexity'])

def outputs(datapoint):
    return extract(datapoint, ['readership'])

if __name__ == "__main__":
    db = Connection().readership_data
    readership = db.readership

    print readership.count(), "14", "2"
    for datapoint in readership.find():
        print " ".join(map(str, inputs(datapoint)))
        print " ".join(map(str, outputs(datapoint)))
