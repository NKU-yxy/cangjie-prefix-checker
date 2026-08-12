func sum_0_072625(limit: Int64): Int64 {
    var total_0_072625: Int64 = 0
    var current_0_072625: Int64 = 0
    while (current_0_072625 < limit) {
        total_0_072625 = total_0_072625 + current_0_072625
        current_0_072625 = current_0_072625 + 1
    }
    total_0_072625
}

main(): Unit {
    let result_0_072625: Int64 = sum_0_072625(6)
    println(result_0_072625)
}
