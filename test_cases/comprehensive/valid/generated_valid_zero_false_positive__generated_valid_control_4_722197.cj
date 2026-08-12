func sum_4_722197(limit: Int64): Int64 {
    var total_4_722197: Int64 = 0
    var current_4_722197: Int64 = 0
    while (current_4_722197 < limit) {
        total_4_722197 = total_4_722197 + current_4_722197
        current_4_722197 = current_4_722197 + 1
    }
    total_4_722197
}

main(): Unit {
    let result_4_722197: Int64 = sum_4_722197(2)
    println(result_4_722197)
}
