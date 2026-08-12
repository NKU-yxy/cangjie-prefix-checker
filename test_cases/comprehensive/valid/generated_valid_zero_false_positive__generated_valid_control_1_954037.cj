func sum_1_954037(limit: Int64): Int64 {
    var total_1_954037: Int64 = 0
    var current_1_954037: Int64 = 0
    while (current_1_954037 < limit) {
        total_1_954037 = total_1_954037 + current_1_954037
        current_1_954037 = current_1_954037 + 1
    }
    total_1_954037
}

main(): Unit {
    let result_1_954037: Int64 = sum_1_954037(5)
    println(result_1_954037)
}
