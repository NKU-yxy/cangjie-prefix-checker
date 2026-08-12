func sum_7_691524(limit: Int64): Int64 {
    var total_7_691524: Int64 = 0
    var current_7_691524: Int64 = 0
    while (current_7_691524 < limit) {
        total_7_691524 = total_7_691524 + current_7_691524
        current_7_691524 = current_7_691524 + 1
    }
    total_7_691524
}

main(): Unit {
    let result_7_691524: Int64 = sum_7_691524(5)
    println(result_7_691524)
}
