func sum_3_885957(limit: Int64): Int64 {
    var total_3_885957: Int64 = 0
    var current_3_885957: Int64 = 0
    while (current_3_885957 < limit) {
        total_3_885957 = total_3_885957 + current_3_885957
        current_3_885957 = current_3_885957 + 1
    }
    total_3_885957
}

main(): Unit {
    let result_3_885957: Int64 = sum_3_885957(3)
    println(result_3_885957)
}
