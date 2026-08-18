import std.collection.*

func singleton(): ArrayList<Int64> {
    ArrayList<Int64>([1])
}

func arrLen(a: Array<Int64>): Int64 {
    a.size
}

func first(a: Array<Int64>): Int64 {
    a[0]
}

func doubleArr(a: Array<Int64>): Array<Int64> {
    [a[0], a[0]]
}

func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(a: Int64, b: Int64): Int64 {
    a + b
}

func padDelta(s: String): String {
    s
}

func padEpsilon(flag: Bool): Bool {
    flag
}

func padZeta(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
}

func padEta(n: Int64): Int64 {
    if (n < 0) {
        0
    } else {
        n
    }
}

main(): Unit {
    let a: ArrayList<Int64> = singleton()
    let arr: Array<Int64> = a.toArray()
    println("len=" + (arrLen(arr)).toString())
    println("first=" + (first(arr)).toString())
    println("dup=" + (doubleArr(arr).size).toString())
    println("pad=" + (padAlpha()).toString())
    let s: String = arr
    println(s)
}
