func sum_2_887597(limit: Int64): Int64 {
    var total_2_887597: Int64 = 0
    var current_2_887597: Int64 = 0
    while (current_2_887597 < limit) {
        total_2_887597 = total_2_887597 + current_2_887597
        current_2_887597 = current_2_887597 + 1
    }
    total_2_887597
}

main(): Unit {
    let result_2_887597: Int64 = sum_2_887597(5)
    println(result_2_887597)
}
