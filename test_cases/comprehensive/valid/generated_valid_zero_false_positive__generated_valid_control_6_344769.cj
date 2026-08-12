func sum_6_344769(limit: Int64): Int64 {
    var total_6_344769: Int64 = 0
    var current_6_344769: Int64 = 0
    while (current_6_344769 < limit) {
        total_6_344769 = total_6_344769 + current_6_344769
        current_6_344769 = current_6_344769 + 1
    }
    total_6_344769
}

main(): Unit {
    let result_6_344769: Int64 = sum_6_344769(3)
    println(result_6_344769)
}
