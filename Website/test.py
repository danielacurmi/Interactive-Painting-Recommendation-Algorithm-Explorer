# merges two sorted lists
def merge_function(list1, list2):
    l1 = len(list1) # 4
    l2 = len(list2) # 3
    l3 = l1 + l2

    combined_list = []
    i = 0
    j = 0
    while((i+j)<l3):
        if(i<l1 and j<l2):
            if(list1[i]<=list2[j]):
                combined_list.append(list1[i])
                i += 1
            else:
                combined_list.append(list2[j])
                j += 1
        else:
            if(i>=l1):
                combined_list.append(list2[j])
                j += 1
            elif(j>=l2):
                combined_list.append(list1[i])
                i += 1
    
    return combined_list

list_1 = [1, 3]
list_2 = [4, 200]

result = merge_function(list_1, list_2)
print(result)
