func sum_5_471861(limit: Int64): Int64 {
    var total_5_471861: Int64 = 0
    var current_5_471861: Int64 = 0
    while (current_5_471861 < limit) {
        total_5_471861 = total_5_471861 + current_5_471861
        current_5_471861 = current_5_471861 + 1
    }
    total_5_471861
}

main(): Unit {
    let result_5_471861: Int64 = sum_5_471861(5)
    println(result_5_471861)
}
